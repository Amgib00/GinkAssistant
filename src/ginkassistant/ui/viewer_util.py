"""Small WebView helpers."""


def stop_webview(web_view) -> None:
    """Stop whatever a WebView is playing. Toga only accepts http(s) URLs
    (so no "about:blank"); loading a tiny empty page does the same job."""
    try:
        web_view.set_content("https://gink.local/blank", "<html><body style='background:#fff'></body></html>")
    except Exception:
        pass
