from .svitlo_placeholder import SvitloProvider
from .ternopil import TernopilProvider

def build_providers():
    return {
        "svitlo": SvitloProvider(),
        "ternopil": TernopilProvider(),
    }
