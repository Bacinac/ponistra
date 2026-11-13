# Conversations

Conversations are short messages among the installation's users: with one colleague, in a group or in a meeting's conversation.

## How to use it

### A new conversation

1. Open [conversations](/chat) on the rail on the left and press {t:chat.new}.
2. In the {t:chat.people} field type your colleagues.
3. For a group, type the {t:chat.groupTitle} if you wish.
4. Press {t:chat.start}. The conversation opens.

### The list of conversations

1. In the left column, under {t:chat.conversations}, conversations are ordered by their last message, and each shows that message and the number of unread ones.
2. Below the list a link leads to contacts.

### A conversation

- {t:meeting.now} in a conversation opens a meeting for it and rings everyone in it. In a meeting's conversation {t:meeting.join} stands in its place.
- {t:meeting.now} in a channel opens a meeting without ringing and posts the message {t:chat.meetingOpened} with the button {t:meeting.join}; whoever joins becomes a member of the channel.
- Beside a direct conversation a dot and {t:chat.online} show that the colleague has Ponistra open, and in a group the header says how many are online.
- {t:meeting.now} in the page's header opens a new meeting without a conversation.
- The menu of a group or a meeting's conversation holds {t:invite.add}, {t:tree.rename} (for a group only, in the {t:chat.renameGroup} window) and {t:chat.leave}. The same menu opens on a right click or a long press on the conversation in the list.

## How it works

A conversation between two people is always one: a new conversation with the same colleague opens the one you already have. A conversation with several colleagues is a group. Every meeting has its own conversation, which stays after the meeting; the meeting's guests write in it too.

When you leave a conversation you no longer see its messages, and someone can add you again. When its last member leaves, the conversation is gone, unless its messages are within a retention period an administrator set. A conversation between two people is not left and gets no new members.

On a wide screen the page opens on the conversation you were last in. While you have no conversation the list says so, and a conversation without messages says {t:chat.empty}

For lasting topics and teams there are [channels](help:chat/channels), which behave differently: an open channel stays even when everyone has left it, and you are told only of mentions and of replies in threads you follow.

## Limits

- Only the installation's users and a meeting's guests take part; people outside the installation cannot be added to a conversation.

## Related

- [Channels](help:chat/channels)
- [Messages in a conversation](help:chat/messages)
- [Reactions](help:chat/reactions)
- [Meetings](help:meetings/overview)
