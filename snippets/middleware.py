class HeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        response['Referrer-Policy'] = 'same-origin'
        response['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if not request.path.startswith('/static/'):
            response['Cache-Control'] = 'no-store'
        return response
