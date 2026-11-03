import django_filters

from .models import ApprovalInstance, ApprovalRule


class ApprovalRuleFilter(django_filters.FilterSet):
    entity_type = django_filters.CharFilter()
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = ApprovalRule
        fields = ["entity_type", "is_active"]


class ApprovalInstanceFilter(django_filters.FilterSet):
    entity_type = django_filters.CharFilter()
    status = django_filters.ChoiceFilter(choices=ApprovalInstance.Status.choices)
    branch = django_filters.NumberFilter(field_name="branch_id")
    # assigned — menga tasdiqlash uchun kelgan (navbat menda); mine — men yuborganlarim
    scope = django_filters.ChoiceFilter(
        choices=[("assigned", "assigned"), ("mine", "mine")], method="filter_scope"
    )

    class Meta:
        model = ApprovalInstance
        fields = ["entity_type", "status", "branch", "scope"]

    def filter_scope(self, queryset, name, value):
        user = self.request.user
        if value == "mine":
            return queryset.filter(requested_by=user)
        # navbat menda: mening bosqichim kutilmoqda va undan oldingi bosqichlar hal bo'lgan
        candidates = queryset.filter(
            status=ApprovalInstance.Status.PENDING, steps__approver=user
        ).distinct()
        ids = []
        for inst in candidates.prefetch_related("steps"):
            current = next((s for s in inst.steps.all() if s.decision == "pending"), None)
            if current and current.approver_id == user.id:
                ids.append(inst.pk)
        return queryset.filter(pk__in=ids)
