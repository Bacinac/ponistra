"""A made-up company, Lipa Studio, and an account of it per language holding something of every
kind: what the help's pictures and the demo show, the same for every run."""

from . import boards, calendar, chat, contacts, documents, links, mail, meetings, notes, tasks

SEEDS = [
    calendar.seed,
    documents.seed,
    mail.seed,
    contacts.seed,
    tasks.seed,
    chat.seed,
    meetings.seed,
    boards.seed,
    links.seed,
    notes.seed,
]
