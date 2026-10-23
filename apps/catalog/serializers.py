from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.branches import selectors as branch_selectors
from apps.currency import selectors as currency_selectors

from .models import Category, PriceType, Product, ProductPrice, Unit


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(
        source="parent.name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "parent",
            "parent_name",
            "sort_order",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate(self, attrs):
        name = attrs.get("name", getattr(self.instance, "name", None))
        parent = attrs.get("parent", getattr(self.instance, "parent", None))
        qs = Category.objects.filter(name__iexact=name, parent=parent)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError({"name": ["Bu nomdagi kategoriya shu darajada bor"]})
        return attrs


@extend_schema_field({"type": "array", "items": {"$ref": "#/components/schemas/CategoryTree"}})
class _CategoryChildrenField(serializers.ListField):
    pass


class CategoryTreeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    sort_order = serializers.IntegerField()
    is_active = serializers.BooleanField()
    parent = serializers.IntegerField(allow_null=True)
    children = _CategoryChildrenField(child=serializers.DictField())


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ["id", "code", "name", "decimal_places", "is_active", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().lower()
        qs = Unit.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value

    def validate_decimal_places(self, value):
        if value > 3:
            raise serializers.ValidationError("Ko'pi bilan 3", code="max_value")
        return value


class PriceTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceType
        fields = ["id", "code", "name", "is_default", "sort_order", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]
        extra_kwargs = {"code": {"validators": []}}

    def validate_code(self, value):
        value = value.strip().lower()
        qs = PriceType.objects.filter(code=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu kod band", code="unique")
        return value


class CurrentPriceSerializer(serializers.Serializer):
    price_type = serializers.CharField()
    price_type_name = serializers.CharField()
    currency = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=4)
    branch = serializers.IntegerField(allow_null=True)
    valid_from = serializers.DateTimeField()


class ProductSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name", read_only=True, default=None, allow_null=True
    )
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_decimal_places = serializers.IntegerField(source="unit.decimal_places", read_only=True)
    prices = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "barcode",
            "name",
            "category",
            "category_name",
            "unit",
            "unit_code",
            "unit_name",
            "unit_decimal_places",
            "min_quantity",
            "description",
            "is_active",
            "prices",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @extend_schema_field(CurrentPriceSerializer(many=True))
    def get_prices(self, product) -> list[dict]:
        prices_map = self.context.get("prices_map") or {}
        return CurrentPriceSerializer(prices_map.get(product.id, []), many=True).data


class ProductWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "sku",
            "barcode",
            "name",
            "category",
            "unit",
            "min_quantity",
            "description",
            "is_active",
        ]
        extra_kwargs = {
            "sku": {"validators": []},
            "barcode": {"required": False, "allow_blank": True},
        }

    def validate_sku(self, value):
        value = value.strip().upper()
        qs = Product.objects.filter(sku=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu artikul band", code="unique")
        return value

    def validate_barcode(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        qs = Product.objects.filter(barcode=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Bu shtrix-kod boshqa tovarda", code="unique")
        return value

    def validate_min_quantity(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Manfiy bo'lmasin", code="min_value")
        return value


class ProductPriceSerializer(serializers.ModelSerializer):
    price_type_code = serializers.CharField(source="price_type.code", read_only=True)
    price_type_name = serializers.CharField(source="price_type.name", read_only=True)
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    branch_name = serializers.CharField(
        source="branch.name", read_only=True, default=None, allow_null=True
    )
    created_by_name = serializers.CharField(
        source="created_by.full_name", read_only=True, default=None, allow_null=True
    )

    class Meta:
        model = ProductPrice
        fields = [
            "id",
            "price_type",
            "price_type_code",
            "price_type_name",
            "currency",
            "currency_code",
            "branch",
            "branch_name",
            "amount",
            "valid_from",
            "created_by",
            "created_by_name",
            "created_at",
        ]
        read_only_fields = fields


class SetPriceSerializer(serializers.Serializer):
    price_type = serializers.PrimaryKeyRelatedField(queryset=PriceType.objects.all())
    currency = serializers.PrimaryKeyRelatedField(queryset=currency_selectors.active_currencies())
    branch = serializers.PrimaryKeyRelatedField(
        queryset=branch_selectors.all_branches(), required=False, allow_null=True
    )
    amount = serializers.DecimalField(max_digits=20, decimal_places=4, min_value=0)
    valid_from = serializers.DateTimeField(required=False)
