from .svitlo_placeholder import SvitloProvider

def build_providers():
    return {
        "svitlo": SvitloProvider(),
    }
