from django.shortcuts import redirect


class CognitoLoginRequiredMiddleware:
    """
    Simple middleware to protect customer pages.

    If there is no access token in the session, redirect to login.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Add any paths you want to protect
        protected_paths = [
            "/customer/orders/new/",
            "/customer/orders/details/",
        ]

        if any(request.path.startswith(p) for p in protected_paths):
            if "access_token" not in request.session:
                print("DEBUG MIDDLEWARE: NO ACCESS TOKEN FOUND")
                print("DEBUG SESSION CONTENT:", request.session.items())
                print("DEBUG REDIRECT PATH:", request.path)
                return redirect("login")


        return self.get_response(request)
