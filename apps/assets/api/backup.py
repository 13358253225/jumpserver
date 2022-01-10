# -*- coding: utf-8 -*-
#
from rest_framework import status, mixins, viewsets
from rest_framework.response import Response

from common.utils import get_object_or_none
from common.permissions import IsOrgAdmin
from orgs.mixins.api import OrgBulkModelViewSet, OrgGenericViewSet

from .. import serializers
from ..tasks import (
    execute_account_backup_plan, start_account_backup_plan_task
)
from ..models import (
    AccountBackupPlan, AccountBackupPlanExecution, AccountBackupPlanTask
)

__all__ = [
    'AccountBackupPlanViewSet', 'AccountBackupPlanExecutionViewSet',
    'AccountBackupPlanExecutionSubtaskViewSet'
]


class AccountBackupPlanViewSet(OrgBulkModelViewSet):
    model = AccountBackupPlan
    filter_fields = ('name',)
    search_fields = filter_fields
    ordering_fields = ('name',)
    ordering = ('name',)
    serializer_class = serializers.AccountBackupPlanSerializer
    permission_classes = (IsOrgAdmin,)


class AccountBackupPlanExecutionViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin,
    mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = serializers.AccountBackupPlanExecutionSerializer
    search_fields = ('trigger', 'plan_id')
    filterset_fields = search_fields
    permission_classes = (IsOrgAdmin,)

    def get_queryset(self):
        queryset = AccountBackupPlanExecution.objects.all()
        return queryset

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pid = serializer.data.get('plan')
        task = execute_account_backup_plan.delay(
            pid=pid, trigger=AccountBackupPlanExecution.Trigger.manual
        )
        return Response({'task': task.id}, status=status.HTTP_201_CREATED)

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        queryset = queryset.order_by('-date_start')
        return queryset


class AccountBackupPlanExecutionSubtaskViewSet(
    mixins.UpdateModelMixin, mixins.ListModelMixin, OrgGenericViewSet
):
    serializer_class = serializers.AccountBackupPlanExecutionTaskSerializer
    permission_classes = (IsOrgAdmin,)
    filter_fields = ['reason']
    search_fields = ['reason']

    def get_queryset(self):
        return AccountBackupPlanTask.objects.all()

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        task = start_account_backup_plan_task.delay(tid=instance.id)
        return Response({'task': task.id})

    def filter_queryset(self, queryset):
        queryset = super().filter_queryset(queryset)
        eid = self.request.GET.get('plan_execution_id')
        execution = get_object_or_none(AccountBackupPlanExecution, pk=eid)
        if execution:
            queryset = queryset.filter(execution=execution)
        queryset = queryset.order_by('is_success', '-date_start')
        return queryset
