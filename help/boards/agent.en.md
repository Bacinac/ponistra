# Sending a board to an agent

The {t:board.agent} button above a board opens a new chat with an agent in your code workspace, with the task of carrying out the answers written on the board.

## How to use it

### The first time

1. Open the board.
2. Press {t:board.agent} on the bar above the board.
3. In the {t:board.agentProject} field choose the project the agent works in and press {t:board.agent}.
4. A new chat opens in the workspace with the task written in. Look it over and start it with Enter.

### After that

1. Press {t:board.agent}. The chat opens in the project you chose the first time.

### Another project

1. In the board's menu choose {t:board.agentFolder}
2. Choose the project and press {t:tree.save}.

## How it works

The task the button writes names the board and asks the agent to carry out the decisions that have an answer written in. Nothing is sent until you press Enter in the chat.

The project is kept with the board, so anyone you share the board with sees it too. Only someone who may edit the board may choose it. The board's own page can neither open a chat nor change the project, as it is closed in a frame of its own.

## Limits

- Only the user the code workspace belongs to sees the button, as the article [Projects](help:agents/projects) describes.
- While no project is chosen, someone who may only read the board does not see the button.
- The projects listed come from the workspace; while it does not answer, no project can be chosen.

## Related

- [Boards](help:boards/overview)
- [Projects](help:agents/projects)
