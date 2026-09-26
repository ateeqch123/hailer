import pytest

from hailer.classify import (
    AUTOREPLY_PHRASES,
    RECRUITER_DOMAINS,
    RECRUITER_WORDS,
    classify,
)


def test_domain_list_and_word_list_are_the_documented_set():
    assert RECRUITER_DOMAINS == (
        "greenhouse.io",
        "lever.co",
        "linkedin.com",
        "indeed.com",
        "ashbyhq.com",
        "myworkday.com",
    )
    assert RECRUITER_WORDS == ("recruiter", "opportunity", "interview", "hiring")
    assert "out of office" in AUTOREPLY_PHRASES
    assert "automatic reply" in AUTOREPLY_PHRASES


@pytest.mark.parametrize(
    "domain",
    [
        "greenhouse.io",
        "jobs.greenhouse.io",
        "lever.co",
        "mail.lever.co",
        "linkedin.com",
        "indeed.com",
        "ashbyhq.com",
        "myworkday.com",
        "wd5.myworkday.com",
    ],
)
def test_recruiter_domains_and_subdomains(domain):
    assert classify({"From": f"Jordan <person@{domain}>"}) == "recruiter"


@pytest.mark.parametrize(
    "sender",
    [
        "person@notgreenhouse.io",
        "person@greenhouse.io.evil.com",
        "person@evilgreenhouse.io",
        "greenhouse.io <person@example.com>",
        "person@example.com",
    ],
)
def test_lookalike_domains_are_ignore_without_keywords(sender):
    assert classify({"From": sender, "Subject": "Hello"}) == "ignore"


@pytest.mark.parametrize("word", ["recruiter", "Recruiter", "opportunities", "interviews", "Hiring"])
def test_recruiter_words_in_subject(word):
    headers = {"From": "ada@example.com", "Subject": f"About the {word} role"}
    assert classify(headers) == "recruiter"


def test_recruiter_word_in_snippet_only():
    assert (
        classify(
            {"From": "ada@example.com", "Subject": "Hello"},
            snippet="A recruiter will write to you next week",
        )
        == "recruiter"
    )


def test_snippet_is_optional():
    assert classify({"From": "ada@example.com", "Subject": "Team update"}) == "ignore"


def test_preinterview_is_not_a_word_match():
    assert classify({"From": "ada@example.com", "Subject": "preinterview notes"}) == "ignore"
    assert classify({"From": "ada@example.com", "Subject": "an opportunistic note"}) == "ignore"


def test_auto_submitted_other_than_no_is_autoreply():
    headers = {
        "From": "bot@greenhouse.io",
        "Subject": "Interview opportunity",
        "Auto-Submitted": "auto-replied",
    }
    assert classify(headers, snippet="hiring") == "autoreply"


@pytest.mark.parametrize("value", ["no", "NO", " no "])
def test_auto_submitted_no_does_not_force_autoreply(value):
    headers = {"From": "ada@example.com", "Subject": "Hiring a backend engineer", "Auto-Submitted": value}
    assert classify(headers) == "recruiter"


def test_out_of_office_subject_beats_recruiter_words():
    headers = {
        "From": "ada@example.com",
        "Subject": "Automatic reply: Interview",
    }
    assert classify(headers) == "autoreply"


def test_ooo_phrase_in_snippet():
    assert (
        classify({"From": "ada@example.com", "Subject": "Re: hello"}, "I am currently out of the office")
        == "autoreply"
    )


def test_precedence_and_list_id_alone_do_not_classify():
    headers = {
        "From": "news@example.com",
        "Subject": "Weekly digest",
        "Precedence": "auto_reply",
        "List-Id": "<news.example.com>",
    }
    assert classify(headers) == "ignore"


def test_list_id_with_hiring_word_is_still_recruiter():
    headers = {
        "From": "news@example.com",
        "Subject": "We are hiring",
        "List-Id": "<jobs.example.com>",
    }
    assert classify(headers) == "recruiter"


def test_header_names_are_case_insensitive_and_first_wins():
    headers = {
        "FROM": "first@greenhouse.io",
        "from": "second@example.com",
        "SUBJECT": "Hello",
    }
    assert classify(headers) == "recruiter"
