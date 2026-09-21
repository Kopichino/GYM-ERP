"""The pagination every list endpoint uses."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Twenty rows a page, as before; a client may ask for more, up to a cap.

    The cap is what keeps any one request bounded. Screens that page through a
    list use the default. The few that genuinely need a whole list -- the member
    picker at the till -- ask for pages of `max_page_size` and walk them, rather
    than being handed an unbounded response.
    """

    page_size_query_param = "page_size"
    max_page_size = 100
