""" Implements a 3 way merge
This is heavily based off:
https://www.mercurial-scm.org/pipermail/mercurial-devel/2006-November/000322.html
"""

import difflib

def drop_absent_lines(diff):
    result = []
    for line in diff:
        if not diff.startswith('?'):
            result.append(line)
    return result

def merge3(base, other, this):
    """ Implements a 3 way merge between BASE, OTHER and THIS
    """
    differ = difflib.Differ()

    # Compare other and this to base
    other_diff = drop_absent_lines(differ.compare(base, other))
    this_diff = drop_absent_lines(differ.compare(base, this))

    result = []
    has_conflict = False

    index_other = 0
    index_this = 0

    # Step through each diff one line at a time
    while index_other < len(other_diff) and index_this < len(this_diff):
        # If the lines match, and the line was either added or not changed on both sides
        if other_diff[index_other] == this_diff[index_this] and
            (other_diff[index_other].startswith('  ') or other_diff[index_other].startswith('+ ')):
            result.append(other_diff[index_other][2:])
            index_other += 1
            index_this += 1
            continue

