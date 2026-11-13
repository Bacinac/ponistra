// Derived from slides.json: `vitest run src/editor/schema.test.ts -u` writes it.
declare const slides: {
  readonly $defs: {
    readonly length: {
      readonly description: "In cm.";
      readonly type: "number";
      readonly minimum: -200;
      readonly maximum: 200;
    };
    readonly extent: {
      readonly description: "In cm.";
      readonly type: "number";
      readonly minimum: 0;
      readonly maximum: 200;
    };
    readonly color: {
      readonly type: "string";
      readonly pattern: "^#[0-9a-f]{6}$";
    };
    readonly blob: {
      readonly type: "string";
      readonly pattern: "^[0-9a-f]{64}$";
    };
    readonly points: {
      readonly type: "number";
      readonly minimum: 1;
      readonly maximum: 400;
    };
    readonly kind: {
      readonly enum: readonly ["title", "content", "two", "section", "titleOnly", "blank"];
    };
    readonly text: {
      readonly description: "How text shows in a box: font is the theme's headings or text font, or a font's name; size the first level's, levels each list level's.";
      readonly type: "object";
      readonly properties: {
        readonly font: {
          readonly type: "string";
          readonly minLength: 1;
          readonly maxLength: 64;
        };
        readonly size: {
          readonly $ref: "#/$defs/points";
        };
        readonly levels: {
          readonly type: "array";
          readonly items: {
            readonly $ref: "#/$defs/points";
          };
          readonly maxItems: 9;
        };
        readonly color: {
          readonly $ref: "#/$defs/color";
        };
        readonly bold: {
          readonly type: "boolean";
        };
        readonly italic: {
          readonly type: "boolean";
        };
        readonly align: {
          readonly enum: readonly ["left", "center", "right", "justify"];
        };
        readonly anchor: {
          readonly enum: readonly ["top", "middle", "bottom"];
        };
      };
      readonly additionalProperties: false;
    };
    readonly box: {
      readonly type: "object";
      readonly properties: {
        readonly x: {
          readonly $ref: "#/$defs/length";
        };
        readonly y: {
          readonly $ref: "#/$defs/length";
        };
        readonly w: {
          readonly $ref: "#/$defs/extent";
        };
        readonly h: {
          readonly $ref: "#/$defs/extent";
        };
        readonly text: {
          readonly $ref: "#/$defs/text";
        };
      };
      readonly required: readonly ["x", "y", "w", "h"];
      readonly additionalProperties: false;
    };
    readonly line: {
      readonly type: "object";
      readonly properties: {
        readonly color: {
          readonly $ref: "#/$defs/color";
        };
        readonly width: {
          readonly description: "In points.";
          readonly type: "number";
          readonly minimum: 0;
          readonly maximum: 100;
        };
      };
      readonly required: readonly ["color", "width"];
      readonly additionalProperties: false;
    };
    readonly shape: {
      readonly description: "Drawn behind the slide's text: a rectangle, ellipse or line (from its box's top left to its bottom right, or bottom left where flipped), an image, a fixed text, the slide's number or the date.";
      readonly type: "object";
      readonly properties: {
        readonly type: {
          readonly enum: readonly ["rect", "ellipse", "line", "image", "text", "number", "date"];
        };
        readonly x: {
          readonly $ref: "#/$defs/length";
        };
        readonly y: {
          readonly $ref: "#/$defs/length";
        };
        readonly w: {
          readonly $ref: "#/$defs/extent";
        };
        readonly h: {
          readonly $ref: "#/$defs/extent";
        };
        readonly fill: {
          readonly $ref: "#/$defs/color";
        };
        readonly line: {
          readonly $ref: "#/$defs/line";
        };
        readonly flip: {
          readonly type: "boolean";
        };
        readonly blob: {
          readonly $ref: "#/$defs/blob";
        };
        readonly content: {
          readonly type: "string";
          readonly maxLength: 1000;
        };
        readonly text: {
          readonly $ref: "#/$defs/text";
        };
      };
      readonly required: readonly ["type", "x", "y", "w", "h"];
      readonly additionalProperties: false;
    };
    readonly background: {
      readonly type: "object";
      readonly properties: {
        readonly color: {
          readonly $ref: "#/$defs/color";
        };
        readonly image: {
          readonly $ref: "#/$defs/blob";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly layout: {
      readonly type: "object";
      readonly properties: {
        readonly id: {
          readonly type: "string";
          readonly pattern: "^[A-Za-z0-9_-]{1,64}$";
        };
        readonly name: {
          readonly type: "string";
          readonly maxLength: 200;
        };
        readonly kind: {
          readonly $ref: "#/$defs/kind";
        };
        readonly background: {
          readonly $ref: "#/$defs/background";
        };
        readonly shapes: {
          readonly type: "array";
          readonly items: {
            readonly $ref: "#/$defs/shape";
          };
          readonly maxItems: 200;
        };
        readonly boxes: {
          readonly type: "object";
          readonly properties: {
            readonly title: {
              readonly $ref: "#/$defs/box";
            };
            readonly subtitle: {
              readonly $ref: "#/$defs/box";
            };
            readonly body: {
              readonly $ref: "#/$defs/box";
            };
            readonly second: {
              readonly $ref: "#/$defs/box";
            };
          };
          readonly additionalProperties: false;
        };
      };
      readonly required: readonly ["id", "kind", "shapes", "boxes"];
      readonly additionalProperties: false;
    };
    readonly size: {
      readonly type: "object";
      readonly properties: {
        readonly width: {
          readonly type: "number";
          readonly minimum: 2.54;
          readonly maximum: 142.24;
        };
        readonly height: {
          readonly type: "number";
          readonly minimum: 2.54;
          readonly maximum: 142.24;
        };
      };
      readonly required: readonly ["width", "height"];
      readonly additionalProperties: false;
    };
  };
  readonly sizes: {
    readonly wide: {
      readonly width: 33.867;
      readonly height: 19.05;
    };
    readonly standard: {
      readonly width: 25.4;
      readonly height: 19.05;
    };
  };
  readonly size: {
    readonly width: 33.867;
    readonly height: 19.05;
  };
  readonly layouts: readonly [{
    readonly id: "title";
    readonly kind: "title";
    readonly shapes: readonly [];
    readonly boxes: {
      readonly title: {
        readonly x: 4.233;
        readonly y: 3.118;
        readonly w: 25.4;
        readonly h: 6.632;
        readonly text: {
          readonly font: "headings";
          readonly size: 54;
          readonly color: "#262626";
          readonly align: "center";
          readonly anchor: "bottom";
        };
      };
      readonly subtitle: {
        readonly x: 4.233;
        readonly y: 10.006;
        readonly w: 25.4;
        readonly h: 4.599;
        readonly text: {
          readonly font: "text";
          readonly size: 24;
          readonly color: "#595959";
          readonly align: "center";
          readonly anchor: "top";
        };
      };
    };
  }, {
    readonly id: "content";
    readonly kind: "content";
    readonly shapes: readonly [{
      readonly type: "number";
      readonly x: 23.918;
      readonly y: 17.657;
      readonly w: 7.62;
      readonly h: 1.014;
      readonly text: {
        readonly font: "text";
        readonly size: 12;
        readonly color: "#8c8c8c";
        readonly align: "right";
        readonly anchor: "middle";
      };
    }];
    readonly boxes: {
      readonly title: {
        readonly x: 2.328;
        readonly y: 1.014;
        readonly w: 29.21;
        readonly h: 3.682;
        readonly text: {
          readonly font: "headings";
          readonly size: 40;
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "middle";
        };
      };
      readonly body: {
        readonly x: 2.328;
        readonly y: 5.071;
        readonly w: 29.21;
        readonly h: 12.087;
        readonly text: {
          readonly font: "text";
          readonly size: 28;
          readonly levels: readonly [28, 24, 20, 20, 20];
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "top";
        };
      };
    };
  }, {
    readonly id: "two";
    readonly kind: "two";
    readonly shapes: readonly [{
      readonly type: "number";
      readonly x: 23.918;
      readonly y: 17.657;
      readonly w: 7.62;
      readonly h: 1.014;
      readonly text: {
        readonly font: "text";
        readonly size: 12;
        readonly color: "#8c8c8c";
        readonly align: "right";
        readonly anchor: "middle";
      };
    }];
    readonly boxes: {
      readonly title: {
        readonly x: 2.328;
        readonly y: 1.014;
        readonly w: 29.21;
        readonly h: 3.682;
        readonly text: {
          readonly font: "headings";
          readonly size: 40;
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "middle";
        };
      };
      readonly body: {
        readonly x: 2.328;
        readonly y: 5.071;
        readonly w: 14.393;
        readonly h: 12.087;
        readonly text: {
          readonly font: "text";
          readonly size: 24;
          readonly levels: readonly [24, 20, 18, 18, 18];
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "top";
        };
      };
      readonly second: {
        readonly x: 17.145;
        readonly y: 5.071;
        readonly w: 14.393;
        readonly h: 12.087;
        readonly text: {
          readonly font: "text";
          readonly size: 24;
          readonly levels: readonly [24, 20, 18, 18, 18];
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "top";
        };
      };
    };
  }, {
    readonly id: "section";
    readonly kind: "section";
    readonly shapes: readonly [];
    readonly boxes: {
      readonly title: {
        readonly x: 2.311;
        readonly y: 4.749;
        readonly w: 29.21;
        readonly h: 7.924;
        readonly text: {
          readonly font: "headings";
          readonly size: 54;
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "bottom";
        };
      };
      readonly body: {
        readonly x: 2.311;
        readonly y: 12.749;
        readonly w: 29.21;
        readonly h: 4.167;
        readonly text: {
          readonly font: "text";
          readonly size: 24;
          readonly color: "#595959";
          readonly align: "left";
          readonly anchor: "top";
        };
      };
    };
  }, {
    readonly id: "titleOnly";
    readonly kind: "titleOnly";
    readonly shapes: readonly [{
      readonly type: "number";
      readonly x: 23.918;
      readonly y: 17.657;
      readonly w: 7.62;
      readonly h: 1.014;
      readonly text: {
        readonly font: "text";
        readonly size: 12;
        readonly color: "#8c8c8c";
        readonly align: "right";
        readonly anchor: "middle";
      };
    }];
    readonly boxes: {
      readonly title: {
        readonly x: 2.328;
        readonly y: 1.014;
        readonly w: 29.21;
        readonly h: 3.682;
        readonly text: {
          readonly font: "headings";
          readonly size: 40;
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "middle";
        };
      };
    };
  }, {
    readonly id: "blank";
    readonly kind: "blank";
    readonly shapes: readonly [];
    readonly boxes: {
      readonly body: {
        readonly x: 2.328;
        readonly y: 1.014;
        readonly w: 29.21;
        readonly h: 16.144;
        readonly text: {
          readonly font: "text";
          readonly size: 28;
          readonly levels: readonly [28, 24, 20, 20, 20];
          readonly color: "#262626";
          readonly align: "left";
          readonly anchor: "top";
        };
      };
    };
  }];
};
export default slides;
