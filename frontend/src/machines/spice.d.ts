declare module '@spice-project/spice-html5' {
  export class SpiceMainConn {
    constructor(options: {
      uri: string;
      password: string;
      screen_id: string;
      onsuccess?: () => void;
      onagent?: (connection: SpiceMainConn) => void;
      onerror?: (error: Error) => void;
    });
    stop(): void;
    inputs?: { state: string; send_msg(message: unknown): void };
    ws?: WebSocket;
  }
  export function resize_helper(connection: SpiceMainConn): void;
}

declare module '@spice-project/spice-html5/src/spicemsg.js' {
  export class SpiceMiniData {
    build_msg(type: number, payload: unknown): void;
  }
  export class SpiceMsgcKeyDown {
    code: number;
  }
  export class SpiceMsgcKeyUp {
    code: number;
  }
}

declare module '@spice-project/spice-html5/src/enums.js' {
  export const Constants: { SPICE_MSGC_INPUTS_KEY_DOWN: number; SPICE_MSGC_INPUTS_KEY_UP: number };
}

declare module '@spice-project/spice-html5/src/atKeynames.js' {
  export const KeyNames: { KEY_LCtrl: number; KEY_Alt: number; KEY_KP_Decimal: number };
}
