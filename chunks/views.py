from chunks.models import Chunk, File
from review.models import Comment, Vote, Star, Task

from django.http import Http404
from django.shortcuts import render, get_object_or_404
from django.template import RequestContext
from django.contrib.auth.decorators import login_required

from pygments import highlight
from pygments.lexers import JavaLexer
from pygments.formatters import HtmlFormatter

@login_required
def view_chunk(request, chunk_id):
    user = request.user
    chunk = get_object_or_404(Chunk, pk=chunk_id)
    user_votes = dict((vote.comment_id, vote.value) \
            for vote in user.votes.filter(comment__chunk=chunk_id))

    def get_comment_data(comment):
        vote = user_votes.get(comment.id, None)
        snippet = chunk.generate_snippet(comment.start, comment.end)
        return (comment, vote, snippet)

    comment_data = map(get_comment_data,
            Comment.get_comments_for_chunk(chunk))

    lexer = JavaLexer()
    formatter = HtmlFormatter(cssclass='syntax', nowrap=True)
    numbers, lines = zip(*chunk.lines)
    # highlight the code this way to correctly identify multi-line constructs
    # TODO implement a custom formatter to do this instead
    highlighted_lines = zip(numbers, 
            highlight('\n'.join(lines), lexer, formatter).split('\n'))
    
    # get the associated task if it exists
    try:
        task = Task.objects.get(chunk=chunk, reviewer=user.get_profile())
        if task.status == 'N':
            # Mark the review task as started if it is currently new
            task.status = 'S'
            task.save()
    except Task.DoesNotExist:
        task = None
    return render(request, 'chunks/view_chunk.html', { 
        'chunk': chunk,
        'highlighted_lines': highlighted_lines,
        'comment_data': comment_data,
        'task': task,
    }) 
