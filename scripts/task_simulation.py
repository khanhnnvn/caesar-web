from __future__ import division

import random
import itertools
import operator
import math
import csv
from collections import defaultdict
from functools import total_ordering

from chunks.models import *


STAFF_PER_STUDENT = 0.05
OTHER_PER_STUDENT = 0.5
REPUTATION_SHAPE = 1.2 # justify this?
REPUTATION_STAFF_SHIFT = 20
ROLE_AFFINITY_MULTIPLIER = 100
REPUTATION_AFFINITY_MULTIPLIER = 0.5

def dot_prod(v1, v2):
    return sum(itertools.imap(operator.mul, v1, v2))


class SimulatedUser:
    def __init__(self, id, role, reputation):
        self.id = id
        self.role = role
        self.reputation = reputation
        self.submissions = []
        self.chunks = []
        self.other_reviewers = set()

    def __unicode__(self):
        return u"User(id=%d, role=%s, reputation=%d)" % \
                (self.id, self.role, self.reputation)

    def __str__(self):
        return unicode(self).encode('utf-8')

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        return self.id == other.id

    def __hash__(self):
        return self.id


class SimulatedSubmission:
    def __init__(self, submission):
        self.chunks = []
        self.reviewers = set()
        for file in submission.files.all():
            # store a link back to the submission for each chunk
            simulated_chunks = (SimulatedChunk(
                chunk=chunk, submission=self) \
                        for chunk in file.chunks.values().all())
            self.chunks.extend(simulated_chunks)
    def __str__(self):
        return unicode(self).encode('utf-8')


@total_ordering
class SimulatedChunk:
    def __init__(self, chunk, submission):
        self._chunk = chunk
        self.name = chunk['name']
        self.submission = submission
        self.reviewers = set()
    def __lt__(self, other):
        pass
    def __eq__(self, other):
        pass
    def assign_reviewer(self, user):
        if user in self.reviewers:
            return False

        self.reviewers.add(user)
        self.submission.reviewers.add(user)
        user.chunks.append(self)

        for reviewer in self.reviewers:
            reviewer.other_reviewers.add(user)
        user.other_reviewers.update(self.reviewers)



def generate_users(student_count, reputation_alpha=REPUTATION_SHAPE):
    role_distribution = (
        ('student', student_count, 0),
        ('staff', int(student_count * STAFF_PER_STUDENT),
            REPUTATION_STAFF_SHIFT),
        ('other', int(student_count * OTHER_PER_STUDENT), 0),
    )

    users = []
    i = 1
    counts = dict((r, 0) for r in zip(*role_distribution)[0])
    for role, n, rep_shift in role_distribution:
        for _ in itertools.repeat(None, n):
            reputation = math.floor(random.paretovariate(reputation_alpha))
            reputation += rep_shift
            user = SimulatedUser(id=i, role=role, reputation=reputation)
            counts[role] += 1
            users.append(user)
            i += 1
    print "User statistics: "
    total = 0
    for role, count in counts.items():
        print "  %s: %d" % (role, count)
        total += count
    print "  total: %d" % total
    return users


def assign_tasks(users, chunks):
    CHUNKS_PER_ROLE = {
            'student': 8,
            'staff': 28,
            'other': 5,
    }
    REVIEWERS_PER_CHUNK = 2

    # simulate random arrival order of users
    random.shuffle(users)
    users.sort(key=lambda u: u.role == 'staff')
    chunks = list(chunks)

    # Sort the chunks according to these criteria:
    # 
    # For students and other:
    #  1. Remove chunks already assigned to the user
    #  2. Remove chunks with maximum number of reviewers
    #  3. Find chunks with largest number of reviewers
    #  4. Sort those chunks by number of reviewers assigned to submission,
    #     which tries to distribute reviewers fairly among submissions.
    #  5. Maximize affinity between user and reviewers on the submission,
    #     which increases diversity of reviewers for submitter.
    #  6. Maximize affinity between user and reviewers on the chunk, which
    #     increases diversity of other reviewers for reviewer.
    #
    # For staff, we simply try to spread them out to maximize number of 
    # submissions with at least one staff member, and then maximize the number
    # of students that get to review a chunk along with staff.

    def compute_affinity(user1, user2):
        distance_affinity = 0
        if user2 in user1.other_reviewers:
            distance_affinity -= 50
        
        reputation_affinity = abs(user1.reputation - user2.reputation)

        role_affinity = 0
        role1, role2 = user1.role, user2.role
        if role1 == 'student' and role2 == 'staff' or \
                role1 == 'staff' and role2 == 'student':
            role_affinity = 2
        elif role1 == 'staff' and role2 == 'staff':
            role_affinity = -100
        else:
            role_affinity = (role1 != role2)
        role_affinity *= ROLE_AFFINITY_MULTIPLIER

        return distance_affinity + reputation_affinity + role_affinity

    def make_chunk_sort_key(user):
        def total_affinity(user, reviewers):
            affinity = 0
            for reviewer in reviewers:
                affinity += compute_affinity(user, reviewer)
            return affinity
        if user.role == 'staff':
            def chunk_sort_key(chunk):
                return (
                    -total_affinity(user, chunk.submission.reviewers),
                    -total_affinity(user, chunk.reviewers),
                )
            return chunk_sort_key
        else:
            def chunk_sort_key(chunk):
                return (
                    user in chunk.reviewers,
                    len(chunk.reviewers) >= REVIEWERS_PER_CHUNK,
                    -len(chunk.reviewers),
                    len(chunk.submission.reviewers),
                    -total_affinity(user, chunk.submission.reviewers),
                    -total_affinity(user, chunk.reviewers),
                )
            return chunk_sort_key

    i = 0
    for user in users:
        key = make_chunk_sort_key(user)
        chunk_count = CHUNKS_PER_ROLE[user.role]
        for _ in itertools.repeat(None, chunk_count):
            chunk_to_assign = min(chunks, key=key)
            chunk_to_assign.assign_reviewer(user)
        i += 1
        print "\r%d users assigned" % i,
    print "\n"


def write_output(output_file, assignment, users, submissions):
    def write(*args):
        for s in args:
            output_file.write(str(s))
        output_file.write("\n")
    def write_header_line(s, level=1):
        write(('==' * level + ' ' + s + ' ').ljust(78, '='))
    write_header_line('Assignment: %s' % assignment.name)
    write()
    write_header_line('Chunk assignments', 2)
    write()
    students_with_staff = 0
    total = 0
    role_counts = {'student': 0, 'staff': 0, 'other': 0}
    for user in users:
        write_header_line(str(user), 3)
        staff_count = sum(r.role == 'staff' for r in user.other_reviewers)
        other_count = sum(r.role == 'other' for r in user.other_reviewers)
        write('Interactions:')
        write('  Staff: %d\n  Other: %d' % (staff_count, other_count))
        write()

        role_counts[user.role] += 1
        if user.role == 'student' and staff_count > 0:
            students_with_staff += 1
        for chunk in user.chunks:
            write('(Submission #%s) %s' % \
                    (chunk.submission.author.id, chunk.name))
            write('  Reviewers assigned to this chunk:')
            for reviewer in chunk.reviewers:
                write('    ', reviewer)
            write()

    write_header_line('Submissions', 2)
    write()
    submissions_with_staff = 0
    submissions_without_reviewers = 0
    minimum_reviewer_count = min(len(s.reviewers) for s in submissions)
    maximum_reviewer_count = max(len(s.reviewers) for s in submissions)
    chunk_reviewer_counts = defaultdict(lambda : 0)
    for submission in submissions:
        for chunk in submission.chunks:
            chunk_reviewer_counts[len(chunk.reviewers)] += 1

        chunk_count = len(submission.chunks)
        write_header_line('Submission #%d' % submission.author.id, 3)
        write('Chunks: %d' % chunk_count)
        chunks_with_reviewers = \
                sum(len(c.reviewers) > 0 for c in submission.chunks)
        if chunk_count == 0:
            coverage = 1
        else:
            coverage = chunks_with_reviewers / chunk_count
        
        write('Coverage: %f%%' % (100 * coverage))
        write()
        write('Reviewers:')
        for reviewer in submission.reviewers:
            write('  ', reviewer)

        submissions_with_staff += \
                any(r.role == 'staff' for r in submission.reviewers)
        if submission.chunks:
            submissions_without_reviewers += (len(submission.reviewers) == 0)
        write()

    write_header_line('Summary statistics', 2)
    write('Population:')
    for role, count in role_counts.items():
        write("  %s: %d" % (role.capitalize(), count))
        total += count
    write("  Total: %d" % total)
    write()
    write('  Students with staff on chunk: %d' % students_with_staff)
    write()
    write('Submissions:')
    write('  Total: %d' % len(submissions))
    write('  Minimum reviewer count: %d' % minimum_reviewer_count)
    write('  Maximum reviewer count: %d' % maximum_reviewer_count)
    write('  Without reviewers: %d' % submissions_without_reviewers)
    write('  With staff reviewers: %d' % submissions_with_staff)
    write()
    write('Chunks')
    for n, count in sorted(chunk_reviewer_counts.items()):
        write('  %d reviewers: %d' % (n, count))
    write()  
    write()


def write_data(output_file, assignment, users, submissions):
    writer = csv.writer(output_file)
    for user in users:
        writer.writerow([user.id, user.role, user.reputation])

    writer.writerow([])
    for submission in submissions:
        for chunk in submission.chunks:
            writer.writerow([chunk.name, len(chunk.reviewers)])


def run():
    with open('task_sim_output.txt', 'w') as f, \
            open('task_sim_data.csv', 'w') as f_data:
        for assignment in Assignment.objects.all():
            print "Running assignment for assignment: %s" % assignment.name
            django_submissions = assignment.submissions \
                    .select_related('files', 'chunks').all()
                    
            chunks = []
            submissions = []
            print "0 chunks loaded",
            for django_submission in django_submissions.all():
                submission = SimulatedSubmission(submission=django_submission)
                if not submission.chunks:
                    # toss out any submissions without chunks
                    continue
                submissions.append(submission)
                chunks.extend(submission.chunks)
                print "\r%d chunks loaded" % (len(chunks),),
            print

            users = generate_users(len(submissions))
            submission_queue = list(submissions)
            for user in users:
                if user.role == 'student':
                    submission = submission_queue.pop()
                    submission.author = user
                    user.submissions.append(submission)
                    if not submission_queue:
                        break

            assign_tasks(users, chunks)
            write_output(f, assignment, users, submissions)
            write_data(f_data, assignment, users, submissions)
            print 
    