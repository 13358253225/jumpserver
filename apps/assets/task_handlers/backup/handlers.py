"""
改密计划：资产改密处理类
"""
import os
import time
import pandas as pd
from collections import defaultdict

from django.utils import timezone
from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from assets.models import AuthBook, Asset, BaseUser, ProtocolsMixin
from assets.notifications import AccountBackupExecutionTaskMsg
from applications.models import Account, Application
from applications.const import AppType
from users.models import User
from common.utils import get_logger
from common.utils.timezone import local_now_display
from common.utils.lock import DistributedLock
from common.utils.file import encrypt_and_compress_zip_file

logger = get_logger(__file__)


class BaseAccountBackupHandler:
    def __init__(self, task):
        self.task = task
        self.is_frozen = False  # 任务状态冻结标志

    def send_escape_mail(self):
        raise NotImplementedError

    def step_perform_task_update(self, is_success, reason, time_start):
        self.task.reason = reason[:1024]
        self.task.is_success = is_success
        self.task.timedelta = time.time() - time_start
        self.task.save()
        logger.info('已完成对任务状态的更新')

    def step_finished(self, is_success):
        if is_success:
            logger.info('任务执行成功')
        else:
            logger.error('任务执行失败')

    def _run(self):
        time_start = time.time()
        self.task.date_start = timezone.now()
        self.task.save()
        is_success = False
        error = '-'
        try:
            self.send_escape_mail()
        except Exception as e:
            self.is_frozen = True
            logger.error('任务执行被异常中断')
            logger.info('下面打印发生异常的 Traceback 信息 : ')
            logger.error(e, exc_info=True)
            error = str(e)
        else:
            is_success = True
        finally:
            reason = error
            self.step_perform_task_update(is_success, reason, time_start)
            self.step_finished(is_success)

    def get_lock_key(self):
        key = f'KEY_LOCK_ESCAPE_ROUTE_PLAN_TASK_RUN_{self.task.id}'
        return key

    def run(self):
        lock_key = self.get_lock_key()
        # 如果10分钟改密任务执行未完成，那么后续相同的任务进来，锁机制将失去意义
        lock = DistributedLock(lock_key, expire=10 * 60)
        logger.info('任务开始: {}'.format(local_now_display()))

        acquired = lock.acquire(timeout=10)
        if not acquired:
            logger.error('任务退出: 锁获取失败')
            return

        time_start = time.time()
        try:
            self._run()
        except Exception as e:
            logger.error('任务运行出现异常')
            logger.error('下面显示异常 Traceback 信息: ')
            logger.error(e, exc_info=True)
        finally:
            logger.info('\n任务结束: {}'.format(local_now_display()))
            timedelta = round((time.time() - time_start), 2)
            logger.info('用时: {}'.format(timedelta))
            if lock.locked():
                lock.release()

    @staticmethod
    def create_secret_row(instance):
        row = {
            getattr(BaseUser, 'username').field.verbose_name: instance.username,
            getattr(BaseUser, 'password').field.verbose_name: instance.password,
            getattr(BaseUser, 'private_key').field.verbose_name: instance.private_key,
            getattr(BaseUser, 'public_key').field.verbose_name: instance.public_key
        }
        return row


class AccountBackupHandler(BaseAccountBackupHandler):
    def create_asset_dfs(self):
        df_dict = defaultdict(list)
        assets = AuthBook.objects.all().prefetch_related('systemuser', 'asset')
        for asset in assets:
            asset.load_auth()
            protocol = asset.asset.protocol
            label_key = getattr(ProtocolsMixin.Protocol, protocol).label
            row = {
                getattr(Asset, 'hostname').field.verbose_name: asset.asset.hostname,
                getattr(Asset, 'ip').field.verbose_name: asset.asset.ip
            }
            secret_row = self.create_secret_row(asset)
            row.update(secret_row)
            df_dict[label_key].append(row)
        for k, v in df_dict.items():
            df_dict[k] = pd.DataFrame(v)
        return df_dict

    def create_app_dfs(self):
        df_dict = defaultdict(list)
        apps = Account.objects.all().prefetch_related('systemuser', 'app')
        for app in apps:
            app.load_auth()
            app_type = app.app.type
            if app_type == 'postgresql':
                label_key = getattr(AppType, 'pgsql').label
            else:
                label_key = getattr(AppType, app_type).label
            row = {
                getattr(Application, 'name').field.verbose_name: app.app.name,
                getattr(Application, 'attrs').field.verbose_name: app.app.attrs
            }
            secret_row = self.create_secret_row(app)
            row.update(secret_row)
            df_dict[label_key].append(row)
        for k, v in df_dict.items():
            df_dict[k] = pd.DataFrame(v)
        return df_dict

    def create_app_asset_excel(self, app_filename, asset_filename):
        logger.info(
            '\n'
            '\033[32m>>> 正在生成资产及应用相关逃生信息文件\033[0m'
            ''
        )
        # Print task start date
        time_start = time.time()
        app_df_dict = self.create_app_dfs()
        asset_df_dict = self.create_asset_dfs()
        info = {app_filename: app_df_dict, asset_filename: asset_df_dict}
        for filename, df_dict in info.items():
            with pd.ExcelWriter(filename) as w:
                for sheet, df in df_dict.items():
                    sheet = sheet.replace(' ', '-')
                    getattr(df, 'to_excel')(w, sheet_name=sheet, index=False)
        timedelta = round((time.time() - time_start), 2)
        logger.info('步骤完成: 用时 {}s'.format(timedelta))

    def send_escape_mail(self):
        recipients = self.task.execution.plan_snapshot.get('recipients')
        if not recipients:
            return
        recipients = User.objects.filter(id__in=list(recipients))
        plan_name = self.task.execution.plan.name
        path = os.path.join(os.path.dirname(settings.BASE_DIR), 'tmp')
        asset_filename = os.path.join(
            path, f'{plan_name}-{_("Asset")}-{local_now_display()}-{time.time()}.xlsx'
        )
        app_filename = os.path.join(
            path, f'{plan_name}-{_("Application")}-{local_now_display()}-{time.time()}.xlsx'
        )
        self.create_app_asset_excel(app_filename, asset_filename)

        logger.info(
            '\n'
            '\033[32m>>> 发送逃生邮件\033[0m'
            ''
        )
        for user in recipients:
            if not user.secret_key:
                attachment_list = []
            else:
                password = user.secret_key.encode('utf8')
                attachment = os.path.join(path, f'{plan_name}-{local_now_display()}-{time.time()}.zip')
                encrypt_and_compress_zip_file(attachment, password, [asset_filename, app_filename])
                attachment_list = [attachment, ]
            AccountBackupExecutionTaskMsg(plan_name, user).publish(attachment_list)
            logger.info('邮件已发送至{}({})'.format(user, user.email))
        os.remove(asset_filename)
        os.remove(app_filename)
