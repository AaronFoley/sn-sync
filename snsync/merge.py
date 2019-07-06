""" Implements a 3 way merge """

import merge3


def merge3_has_conflict(mine, base, your, reprocess=False):
    """ Reimplementing Merge3.merge_lines to return a has conflict """

    had_conflict = False
    results = []

    merge = merge3.Merge3(base, mine, your)

    # Workout the new line standard to use
    newline = '\n'
    if len(base) > 0:
        if base[0].endswith('\r\n'):
            newline = '\r\n'
        elif base[0].endswith('\r'):
            newline = '\r'

    start_marker = '<<<<<<< local'
    mid_marker = '======='
    end_marker = '>>>>>>> remote'

    merge_regions = merge.merge_regions()
    if reprocess is True:
        merge_regions = merge.reprocess_merge_regions(merge_regions)
    for t in merge_regions:
        what = t[0]
        if what == 'unchanged':
            results.extend(base[t[1]:t[2]])
        elif what == 'a' or what == 'same':
            results.extend(mine[t[1]:t[2]])
        elif what == 'b':
            results.extend(your[t[1]:t[2]])
        elif what == 'conflict':
            results.append(start_marker + newline)
            results.extend(mine[t[1]:t[2]])
            results.append(mid_marker + newline)
            results.extend(your[t[1]:t[2]])
            results.append(end_marker + newline)
            had_conflict = True
        else:
            raise ValueError(what)

    return had_conflict, results
