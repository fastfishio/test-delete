from libutil.util import AutoNameEnum
from enum import auto


class ResourceType(AutoNameEnum):
    PLATFORM = auto()
    CUSTOMER_SERVICE = auto()


class RoleType(AutoNameEnum):
    # general
    ADMIN = auto()

    # cs
    CS_EMPTY = auto()
    CS_LEVEL_1 = auto()
    CS_LEADER = auto()


class Permission(AutoNameEnum):

    # customer support
    CS_ORDER_SEARCH = auto()
    CS_ORDER_DETAILS = auto()
    CS_ORDER_COMMENT = auto()
    CS_ADJUST_PAYMENT = auto()
    CS_ISSUE_CREDIT = auto()
    CS_CANCEL_ORDER = auto()
