from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from core.api.mixins import CapabilityViewSetMixin
from core.api.schema import ERROR_RESPONSE
from core.api.security import check_origin

from . import selectors, services
from .cookies import delete_refresh_cookie, get_refresh_cookie, set_refresh_cookie
from .models import Role, User
from .serializers import (
    CapabilitySerializer,
    ChangePasswordSerializer,
    LoginResponseSerializer,
    LoginSerializer,
    MeSerializer,
    RefreshResponseSerializer,
    RoleSerializer,
    SetPasswordSerializer,
    UserSerializer,
    UserWriteSerializer,
)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(
        request=LoginSerializer,
        responses={200: LoginResponseSerializer, 401: ERROR_RESPONSE, 429: ERROR_RESPONSE},
        tags=["auth"],
        summary="Kirish: access token + httpOnly refresh cookie",
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.authenticate_user(**serializer.validated_data)
        access, refresh = services.issue_tokens(user)
        response = Response({"access": access, "user": selectors.me_payload(user)})
        set_refresh_cookie(response, refresh)
        return response


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        request=None,
        responses={200: RefreshResponseSerializer, 401: ERROR_RESPONSE, 403: ERROR_RESPONSE},
        tags=["auth"],
        summary="Refresh cookie orqali yangi access (refresh aylantiriladi)",
    )
    def post(self, request):
        check_origin(request)
        raw = get_refresh_cookie(request)
        if not raw:
            raise AuthenticationFailed(
                {"detail": "Refresh token yo'q", "code": "token_not_valid"}, code="token_not_valid"
            )
        try:
            access, refresh = services.rotate_refresh_token(raw)
        except TokenError as exc:
            response_exc = AuthenticationFailed(
                {"detail": str(exc), "code": "token_not_valid"}, code="token_not_valid"
            )
            raise response_exc from None
        response = Response({"access": access})
        set_refresh_cookie(response, refresh)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=None, responses={204: None}, tags=["auth"], summary="Chiqish")
    def post(self, request):
        check_origin(request)
        services.revoke_refresh_token(get_refresh_cookie(request))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        delete_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer, tags=["auth"])
    def get(self, request):
        return Response(MeSerializer(selectors.me_payload(request.user)).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses={204: None}, tags=["auth"])
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        services.change_password(
            actor=request.user,
            user=request.user,
            new_password=serializer.validated_data["new_password"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CapabilityListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=CapabilitySerializer(many=True), tags=["auth"])
    def get(self, request):
        return Response(CapabilitySerializer(selectors.capabilities_payload(), many=True).data)


@extend_schema(tags=["users"])
class UserViewSet(
    CapabilityViewSetMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.none()
    serializer_class = UserSerializer
    capability_map = {"*": "users.manage"}
    filterset_fields = ["role", "is_active"]
    search_fields = ["username", "full_name", "phone"]
    ordering_fields = ["full_name", "username", "date_joined"]
    ordering = ["full_name"]

    def get_queryset(self):
        return selectors.users_queryset()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return UserWriteSerializer
        if self.action == "set_password":
            return SetPasswordSerializer
        return UserSerializer

    @extend_schema(request=UserWriteSerializer, responses={201: UserSerializer})
    def create(self, request, *args, **kwargs):
        serializer = UserWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.create_user(actor=request.user, **serializer.validated_data)
        user = selectors.users_queryset().get(pk=user.pk)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=UserWriteSerializer, responses={200: UserSerializer})
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        user = self.get_object()
        serializer = UserWriteSerializer(user, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = services.update_user(actor=request.user, user=user, **serializer.validated_data)
        user = selectors.users_queryset().get(pk=user.pk)
        return Response(UserSerializer(user).data)

    @extend_schema(request=SetPasswordSerializer, responses={204: None})
    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(
            actor=request.user, user=user, new_password=serializer.validated_data["new_password"]
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


@extend_schema(tags=["roles"])
class RoleViewSet(CapabilityViewSetMixin, viewsets.ModelViewSet):
    queryset = Role.objects.none()
    serializer_class = RoleSerializer
    capability_map = {"list": "users.manage", "retrieve": "users.manage", "*": "users.manage"}
    search_fields = ["code", "name"]
    ordering = ["name"]

    def get_queryset(self):
        return selectors.roles_queryset()

    def perform_create(self, serializer):
        role = services.create_role(actor=self.request.user, **serializer.validated_data)
        serializer.instance = selectors.roles_queryset().get(pk=role.pk)

    def perform_update(self, serializer):
        role = services.update_role(
            actor=self.request.user, role=serializer.instance, **serializer.validated_data
        )
        serializer.instance = selectors.roles_queryset().get(pk=role.pk)

    def perform_destroy(self, instance):
        services.delete_role(actor=self.request.user, role=instance)
