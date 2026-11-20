from dataclasses import dataclass


@dataclass
class Bad:
    cases: list = None

    def __post_init__(self):
        if self.cases is None:
            self.cases = []


a = Bad()
b = Bad()
a.cases.append("C-1")
print(b.cases)  # what do you expect?
print(a.cases)
