from django.conf.urls.defaults import *

urlpatterns = patterns('caesar.comments.views',
    (r'^new/', 'new'),
	(r'^reply/', 'reply'),
    (r'^delete/', 'delete'),
    (r'^vote/', 'vote'),
    (r'^unvote/', 'unvote'),
)
