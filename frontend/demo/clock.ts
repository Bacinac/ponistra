/** The demo's clock runs on from the moment the walk recorded, so the days its answers were asked
 * for (today, this week's calendar, how long ago a mail came) are the days the app asks for. */
export function installClock(at: string): void {
  const recorded = Date.parse(at);
  if (Number.isNaN(recorded)) throw new Error(`The recording's moment ${at} is not a date`);
  const RealDate = Date;
  const offset = recorded - RealDate.now();
  const now = () => RealDate.now() + offset;

  class DemoDate extends RealDate {
    constructor(...given: unknown[]) {
      if (given.length === 0) super(now());
      else super(...(given as [string | number | Date]));
    }

    static override now(): number {
      return now();
    }

    // A date the browser itself makes (a file's, IndexedDB's) is a date as much as one made here.
    static [Symbol.hasInstance](value: unknown): boolean {
      return value instanceof RealDate;
    }
  }

  // Called without new, Date gives the moment as text.
  const DemoDateCalled = new Proxy(DemoDate, {
    apply: () => new DemoDate().toString(),
  });
  window.Date = DemoDateCalled as DateConstructor;
}
