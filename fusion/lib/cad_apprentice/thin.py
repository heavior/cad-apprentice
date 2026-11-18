# Parts that may print thinner than one line of the nozzle. Sizes set as shares of a parent part
# (fusion/rules.md rule 9) can end up very small on a small model. That can be fine, so this only
# reports: it never fails a build or a trial. The checks are plain Python, so test_thin.py runs anywhere.

NOZZLE_MM = 0.4  # one line of a 0.4 mm nozzle


def below(found, floor=NOZZLE_MM):
    # [(name, mm)] -> the ones under floor, thinnest first.
    return sorted(((n, v) for n, v in found if v < floor - 1e-9), key=lambda x: x[1])


# [(name, mm)] -> 'name 0.21 mm, ...' for the log.
def text(found):
    return ', '.join('%s %.2f mm' % (n, v) for n, v in found)


def sizes(des, names):
    # Each named parameter's value in mm. Raises on a name the design lacks, so a typo doesn't hide a part.
    found = []
    for n in names:
        p = des.userParameters.itemByName(n)
        if not p:
            raise Exception('thin watch: no parameter %s' % n)
        found.append((n, p.value * 10))  # the API works in cm
    return found


class Watch:
    # Call it after the build and after each trial: it logs the parts under the floor as THIN and keeps
    # the thinnest. summary() logs how many checks had any.
    def __init__(self, names, log, floor=NOZZLE_MM):
        self.names, self.log, self.floor = list(names), log, floor
        self.checks, self.hits, self.thinnest = 0, 0, None

    def __call__(self, des, label):
        return self.note(sizes(des, self.names), label)

    # Logs the parts in found that are under the floor, keeps the thinnest, and returns them.
    def note(self, found, label):
        thin = below(found, self.floor)
        self.checks += 1
        if thin:
            self.hits += 1
            self.log.append('THIN (under %g mm) %s: %s' % (self.floor, label, text(thin)))
            if self.thinnest is None or thin[0][1] < self.thinnest[1]:
                self.thinnest = thin[0] + (label,)
        return thin

    # One line on all the checks so far, logged and returned.
    def summary(self):
        if not self.hits:
            line = 'thin parts: none under %g mm in %d checks' % (self.floor, self.checks)
        else:
            n, v, label = self.thinnest
            line = 'thin parts: %d of %d checks had parts under %g mm; thinnest %s %.2f mm (%s)' % (
                self.hits, self.checks, self.floor, n, v, label)
        self.log.append(line)
        return line
