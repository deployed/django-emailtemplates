from django.core.exceptions import PermissionDenied


class AnyPermissionRequiredMixin:
    """
    Requires ANY of `permissions`, unlike Django's `PermissionRequiredMixin`, which
    requires all: in the admin the change permission includes viewing.
    """

    permissions = ()

    def dispatch(self, request, *args, **kwargs):
        if not any(request.user.has_perm(perm) for perm in self.permissions):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
