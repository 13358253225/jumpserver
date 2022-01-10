# -*- coding: utf-8 -*-
#
from django.utils.translation import ugettext as _
from rest_framework import serializers

from orgs.mixins.serializers import BulkOrgResourceModelSerializer
from ops.mixin import PeriodTaskSerializerMixin
from common.utils import get_logger

from ..models import (
    AccountBackupPlan,
    AccountBackupPlanExecution,
    AccountBackupPlanTask,
)

logger = get_logger(__file__)

__all__ = [
    'AccountBackupPlanSerializer', 'AccountBackupPlanExecutionSerializer',
    'AccountBackupPlanExecutionTaskSerializer'
]


class AccountBackupPlanSerializer(PeriodTaskSerializerMixin, BulkOrgResourceModelSerializer):
    class Meta:
        model = AccountBackupPlan
        fields = [
            'id', 'name', 'is_periodic', 'interval', 'crontab', 'date_created',
            'date_updated', 'created_by', 'periodic_display', 'comment',
            'recipients'
        ]
        extra_kwargs = {
            'name': {'required': True},
            'periodic_display': {'label': _('Periodic perform')},
            'recipients': {'label': _('Recipient'), 'help_text': _(
                'Currently only mail sending is supported'
            )}
        }


class AccountBackupPlanExecutionSerializer(serializers.ModelSerializer):
    trigger_display = serializers.ReadOnlyField(
        source='get_trigger_display', label=_('Trigger mode')
    )

    class Meta:
        model = AccountBackupPlanExecution
        fields = '__all__'
        read_only_fields = (
            'plan_snapshot', 'date_start', 'timedelta', 'date_created'
        )

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        fields.extend(['recipients', ])
        return fields


class AccountBackupPlanExecutionTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountBackupPlanTask
        fields = '__all__'
