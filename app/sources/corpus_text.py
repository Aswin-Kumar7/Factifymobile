"""Text helpers shared by retrieval and reasoning.

`is_navigation` lives here rather than in either caller because both need it and
they must agree. Retrieval uses it to avoid quoting a breadcrumb as evidence;
reasoning uses it to avoid spending a metered model call on a menu.
"""

from __future__ import annotations


def is_navigation(sentence: str) -> bool:
    """Whether a line is site chrome rather than prose.

    Extraction sometimes carries the nav bar into the body, and a breadcrumb like
    "Home | News | Kerala Jail Gets AI Based Smart Surveillance System" scores
    extremely well on word overlap precisely because it is the headline repeated.
    It was the top-scoring "evidence" for one probe at 83% coverage.

    Quoting it is wrong on its own terms: a citation should point at the sentence
    where a publication says a thing, not at the menu above it.
    """
    if sentence.count("|") >= 2 or sentence.count("»") >= 2:
        return True
    # Breadcrumbs and menus are title-case fragments without sentence punctuation.
    words = sentence.split()
    if len(words) >= 5 and "." not in sentence:
        capitalised = sum(1 for w in words if w[:1].isupper())
        if capitalised / len(words) > 0.8:
            return True
    return False
