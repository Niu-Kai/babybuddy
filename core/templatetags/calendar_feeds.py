from django import template
from core.calendar_tokens import feed_token

register = template.Library()


@register.simple_tag
def calendar_feed_token(user, child):
    return feed_token(user, child)
