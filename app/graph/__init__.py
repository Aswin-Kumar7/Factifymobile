"""Evidence graph (M38-M39).

Two modules and one rule between them.

`promotion` writes an observation for every request and promotes almost none of
them. `recurrence` reads only what was promoted. The gap between the two is
deliberate: it is what stops a recurrence counter from being something an attacker
can inflate by submitting the same thing repeatedly.
"""
