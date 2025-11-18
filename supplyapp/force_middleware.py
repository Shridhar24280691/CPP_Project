class ForceSameSiteMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if "sessionid" in response.cookies:
            response.cookies["sessionid"]["samesite"] = "None"
            response.cookies["sessionid"]["secure"] = True

        if "csrftoken" in response.cookies:
            response.cookies["csrftoken"]["samesite"] = "None"
            response.cookies["csrftoken"]["secure"] = True

        return response
