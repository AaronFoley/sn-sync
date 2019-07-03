""" Implements a 3 way merge
This is heavily based off:
https://www.mercurial-scm.org/pipermail/mercurial-devel/2006-November/000322.html
"""

import difflib
from pprint import pprint

def drop_absent_lines(diff):
    result = []
    for line in diff:
        if not line.startswith('?'):
            result.append(line)
    return result

def merge3(base, other, this):
    """ Implements a 3 way merge between BASE, OTHER and THIS
    """
    differ = difflib.Differ()

    # Compare other and this to base
    other_diff = drop_absent_lines(differ.compare(base, other))
    this_diff = drop_absent_lines(differ.compare(base, this))

    pprint(other_diff)
    pprint(this_diff)

    result = []
    has_conflict = False

    index_other = 0
    index_this = 0

    # Step through each diff one line at a time
    while index_other < len(other_diff) and index_this < len(this_diff):
        print(f"Indexes: other:{index_other} this:{index_this}")
        print("Comparing lines:")
        print("    other: " + other_diff[index_other])
        print("    this: " + this_diff[index_this])

        # If the lines match, and the line was either added or not changed on both sides
        if (other_diff[index_other] == this_diff[index_this] and
            (other_diff[index_other].startswith('  ') or other_diff[index_other].startswith('+ '))):
            result.append(other_diff[index_other][2:])
            index_other += 1
            index_this += 1
            continue

        # Lines matching on both sides, but getting removed
        if (other_diff[index_other] == this_diff[index_this] and
            other_diff[index_other].startswith('- ')):
            index_other += 1
            index_this += 1
            continue

        # Line added to other
        if other_diff[index_other].startswith('+ ') and this_diff[index_this].startswith('  '):
            result.append(other_diff[index_other][2:])
            index_other += 1
            continue

        # adding line in this
        if this_diff[index_this].startswith('+ ') and other_diff[index_other].startswith('  '):
            result.append(this_diff[index_this][2:])
            index_this += 1
            continue

        print("CONFLICT")
        break

        # Conflict
        result.append("<<<<<<< OTHER\n")
        while (index_other < len(other_diff)) and not other_diff[index_other].startswith('  '):
            result.append(other_diff[index_other][2:])
            index_other += 1
        result.append("=======\n")
        while (index_this < len(this_diff)) and not this_diff[index_this].startswith('  '):
            result.append(this_diff[index_this][2:])
            index_this += 1
        result.append(">>>>>>> THIS\n")
        had_conflict = True

    # append remining lines - there will be only either A or B
    for i in range(len(other_diff) - index_other):
        result.append(other_diff[index_other + i][2:])
    for i in range(len(this_diff) - index_this):
        result.append(this_diff[index_this + i][2:])

    return had_conflict, result

def read_file(filename):
    try:
        f = open(filename, 'rb')
        l = f.readlines()
        f.close()
    except:
        print("can't open file '" + filename + "'. aborting.")
        sys.exit(-1)
    else:
        return l

# Temp Main
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 4:
        print('mymerge.py base other my [merged]')
        sys.exit(-1)

    base = read_file(sys.argv[1])
    other = read_file(sys.argv[2])
    this = read_file(sys.argv[3])

    had_conflict, result = merge3(base, other, this)

    for line in result:
        print(line)

    if had_conflict:
        sys.exit(-1)
