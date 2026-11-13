// Derived from schema.json: `vitest run src/editor/schema.test.ts -u` writes it.
declare const schema: {
  readonly $defs: {
    readonly color: {
      readonly description: "A palette's colour by its name, or an imported file's own as #rrggbb, whose dark shade the editor derives.";
      readonly type: "string";
      readonly pattern: "^(#[0-9a-f]{6}|[a-z]+)$";
    };
    readonly id: {
      readonly type: "string";
      readonly pattern: "^[A-Za-z0-9_-]{1,64}$";
    };
    readonly level: {
      readonly enum: readonly [1, 2, 3, 4];
    };
    readonly align: {
      readonly enum: readonly ["left", "center", "right", "justify"];
    };
    readonly indent: {
      readonly description: "In cm from the text's left edge; step is one indent step, as Word steps a paragraph in.";
      readonly type: "number";
      readonly minimum: 0;
      readonly maximum: 10;
      readonly step: 1.25;
    };
    readonly list: {
      readonly enum: readonly ["bullet", "number", "check"];
    };
    readonly note: {
      readonly enum: readonly ["foot", "end"];
    };
    readonly tabKind: {
      readonly enum: readonly ["left", "center", "right", "decimal"];
    };
    readonly leader: {
      readonly enum: readonly ["dot", "hyphen", "underscore"];
    };
    readonly tabStop: {
      readonly description: "A tab stop, at its distance in cm from the text's left edge, where Word measures it from the margin.";
      readonly type: "object";
      readonly properties: {
        readonly at: {
          readonly type: "number";
          readonly minimum: 0;
          readonly maximum: 60;
        };
        readonly kind: {
          readonly $ref: "#/$defs/tabKind";
        };
        readonly leader: {
          readonly $ref: "#/$defs/leader";
        };
      };
      readonly required: readonly ["at", "kind"];
      readonly additionalProperties: false;
    };
    readonly field: {
      readonly enum: readonly ["page", "pages", "title", "date"];
    };
    readonly chartKind: {
      readonly enum: readonly ["column", "bar", "line", "area", "pie", "doughnut", "scatter"];
    };
    readonly stacking: {
      readonly enum: readonly ["column", "bar", "line", "area"];
    };
    readonly point: {
      readonly type: "object";
      readonly properties: {
        readonly row: {
          readonly $ref: "#/$defs/id";
        };
        readonly col: {
          readonly $ref: "#/$defs/id";
        };
      };
      readonly required: readonly ["row", "col"];
      readonly additionalProperties: false;
    };
    readonly tableName: {
      readonly type: "string";
      readonly maxLength: 31;
      readonly pattern: "^[^\\u0000-\\u001f\\\\\\[\\]:*?/'](?:[^\\u0000-\\u001f\\\\\\[\\]:*?/]*[^\\u0000-\\u001f\\\\\\[\\]:*?/'])?$";
    };
    readonly chartTitle: {
      readonly type: "string";
      readonly maxLength: 200;
    };
    readonly cellTo: {
      readonly type: "string";
      readonly pattern: "^[A-Za-z0-9_-]{1,64}:[A-Za-z0-9_-]{1,64}$";
    };
    readonly line: {
      readonly description: "A row or a column a formula refers to: by id, or @ for the one its own cell is in.";
      readonly anyOf: readonly [{
        readonly $ref: "#/$defs/id";
      }, {
        readonly const: "@";
      }];
    };
    readonly end: {
      readonly description: "An end of a formula's reference: its row, its column or both, each fixed where it is written with $.";
      readonly type: "object";
      readonly properties: {
        readonly row: {
          readonly $ref: "#/$defs/line";
        };
        readonly col: {
          readonly $ref: "#/$defs/line";
        };
        readonly absRow: {
          readonly const: true;
        };
        readonly absCol: {
          readonly const: true;
        };
      };
      readonly anyOf: readonly [{
        readonly required: readonly ["row"];
      }, {
        readonly required: readonly ["col"];
      }];
      readonly additionalProperties: false;
    };
    readonly reference: {
      readonly description: "A formula's reference, to its own table or to the one named, from one end to the other.";
      readonly type: "object";
      readonly properties: {
        readonly table: {
          readonly $ref: "#/$defs/id";
        };
        readonly from: {
          readonly $ref: "#/$defs/end";
        };
        readonly to: {
          readonly $ref: "#/$defs/end";
        };
      };
      readonly required: readonly ["from"];
      readonly additionalProperties: false;
    };
    readonly formula: {
      readonly description: "A formula in pieces: its text in the canonical form, each reference by the ids of its rows and columns.";
      readonly type: "array";
      readonly items: {
        readonly anyOf: readonly [{
          readonly type: "string";
          readonly minLength: 1;
        }, {
          readonly $ref: "#/$defs/reference";
        }];
      };
      readonly minItems: 1;
    };
    readonly definedName: {
      readonly description: "A defined name of a document (D16): the name formulas use, unique in its scope ignoring case, the formula it stands for, and the table it is in force in alone where it is not in force in the whole document.";
      readonly type: "object";
      readonly properties: {
        readonly name: {
          readonly type: "string";
          readonly minLength: 1;
          readonly maxLength: 255;
        };
        readonly pieces: {
          readonly $ref: "#/$defs/formula";
        };
        readonly table: {
          readonly $ref: "#/$defs/id";
        };
      };
      readonly required: readonly ["name", "pieces"];
      readonly additionalProperties: false;
    };
    readonly look: {
      readonly description: "The look of a light cell, or of a row's or a column's, which a light cell in it without one of its own shows: the marks over all of its text, its paragraph's attributes and the cell's fill.";
      readonly type: "object";
      readonly properties: {
        readonly marks: {
          readonly type: "object";
          readonly minProperties: 1;
        };
        readonly attrs: {
          readonly type: "object";
          readonly minProperties: 1;
        };
        readonly fill: {
          readonly $ref: "#/$defs/tint";
        };
        readonly edges: {
          readonly $ref: "#/$defs/edges";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly gridCell: {
      readonly description: "A cell of a table's grid beside the text (D16): what was typed into it where it has no node, its formula in pieces by row and column id, its number format, the look of its text where it has no node, with nothing in it where the cell is plain in a row or a column that has one, and the slot it is merged down and right to.";
      readonly type: "object";
      readonly properties: {
        readonly text: {
          readonly type: "string";
          readonly minLength: 1;
        };
        readonly formula: {
          readonly $ref: "#/$defs/formula";
        };
        readonly format: {
          readonly type: "string";
          readonly minLength: 1;
        };
        readonly look: {
          readonly anyOf: readonly [{
            readonly $ref: "#/$defs/look";
          }, {
            readonly const: {};
          }];
        };
        readonly to: {
          readonly $ref: "#/$defs/cellTo";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly author: {
      readonly description: "The author's name as the change keeps it, as Word does.";
      readonly type: "string";
      readonly minLength: 1;
      readonly maxLength: 200;
    };
    readonly user: {
      readonly description: "The author's account, where the author is one of ours.";
      readonly type: readonly ["integer", "null"];
    };
    readonly date: {
      readonly description: "When the change was made, in ISO 8601.";
      readonly type: readonly ["string", "null"];
    };
    readonly change: {
      readonly description: "A proposed change: the proposal it is part of, its author and when it was made.";
      readonly type: "object";
      readonly properties: {
        readonly id: {
          readonly $ref: "#/$defs/id";
        };
        readonly author: {
          readonly $ref: "#/$defs/author";
        };
        readonly user: {
          readonly $ref: "#/$defs/user";
        };
        readonly date: {
          readonly $ref: "#/$defs/date";
        };
      };
      readonly required: readonly ["id", "author"];
      readonly additionalProperties: false;
    };
    readonly marks: {
      readonly description: "Marks by their names, each with its attributes.";
      readonly type: "object";
      readonly additionalProperties: {
        readonly type: "object";
      };
    };
    readonly stroke: {
      readonly description: "A line's style: ECMA-376's (§17.18.2), which Excel's and PowerPoint's map onto, with Excel's hair and slantDashDot.";
      readonly enum: readonly ["single", "thick", "double", "dotted", "dashed", "dotDash", "dotDotDash", "triple", "thinThickSmallGap", "thickThinSmallGap", "thinThickThinSmallGap", "thinThickMediumGap", "thickThinMediumGap", "thinThickThinMediumGap", "thinThickLargeGap", "thickThinLargeGap", "thinThickThinLargeGap", "wave", "doubleWave", "dashSmallGap", "dashDotStroked", "threeDEmboss", "threeDEngrave", "outset", "inset", "hair", "slantDashDot"];
    };
    readonly edge: {
      readonly description: "A line on an edge, its width in points, in the text's colour where it names none; or none, which takes away a line beneath it.";
      readonly anyOf: readonly [{
        readonly const: "none";
      }, {
        readonly type: "object";
        readonly properties: {
          readonly line: {
            readonly $ref: "#/$defs/stroke";
          };
          readonly width: {
            readonly type: "number";
            readonly exclusiveMinimum: 0;
            readonly maximum: 100;
          };
          readonly color: {
            readonly $ref: "#/$defs/color";
          };
        };
        readonly required: readonly ["line", "width"];
        readonly additionalProperties: false;
      }];
    };
    readonly edges: {
      readonly description: "A cell's own edges, over its table's design.";
      readonly type: "object";
      readonly properties: {
        readonly top: {
          readonly $ref: "#/$defs/edge";
        };
        readonly bottom: {
          readonly $ref: "#/$defs/edge";
        };
        readonly left: {
          readonly $ref: "#/$defs/edge";
        };
        readonly right: {
          readonly $ref: "#/$defs/edge";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly regionEdges: {
      readonly description: "The edges round a region of cells, and insideH and insideV between its cells.";
      readonly type: "object";
      readonly properties: {
        readonly top: {
          readonly $ref: "#/$defs/edge";
        };
        readonly bottom: {
          readonly $ref: "#/$defs/edge";
        };
        readonly left: {
          readonly $ref: "#/$defs/edge";
        };
        readonly right: {
          readonly $ref: "#/$defs/edge";
        };
        readonly insideH: {
          readonly $ref: "#/$defs/edge";
        };
        readonly insideV: {
          readonly $ref: "#/$defs/edge";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly tint: {
      readonly description: "A colour as $defs.color, or a file's own with its alpha (#rrggbbaa), laid over what is beneath it; none fills nothing, showing what is beneath.";
      readonly type: "string";
      readonly pattern: "^(#[0-9a-f]{6}([0-9a-f]{2})?|[a-z]+)$";
    };
    readonly valign: {
      readonly enum: readonly ["top", "center", "bottom"];
    };
    readonly part: {
      readonly description: "A part of a table's design: its cells' fill, the marks over its text (false takes away one a part beneath set), its capitals, its paragraphs' and its cells' alignment, and its edges.";
      readonly type: "object";
      readonly properties: {
        readonly fill: {
          readonly $ref: "#/$defs/tint";
        };
        readonly marks: {
          readonly type: "object";
          readonly minProperties: 1;
          readonly additionalProperties: {
            readonly anyOf: readonly [{
              readonly type: "object";
            }, {
              readonly const: false;
            }];
          };
        };
        readonly caps: {
          readonly enum: readonly ["all", "small", "none"];
        };
        readonly align: {
          readonly $ref: "#/$defs/align";
        };
        readonly valign: {
          readonly $ref: "#/$defs/valign";
        };
        readonly edges: {
          readonly $ref: "#/$defs/regionEdges";
        };
      };
      readonly minProperties: 1;
      readonly additionalProperties: false;
    };
    readonly bandSizes: {
      readonly description: "The size of the first band and of the second; 0 where bands never show, as in Word's style that names no size.";
      readonly type: "array";
      readonly items: {
        readonly type: "integer";
        readonly minimum: 0;
        readonly maximum: 99;
      };
      readonly minItems: 2;
      readonly maxItems: 2;
    };
    readonly design: {
      readonly description: "A table's design (D30): its parts' looks, the switches that turn them on, its bands' sizes, Word's table lines under every part, PowerPoint's background and shadow, Word's spacing between cells and the shading between them, the style it came from, the program whose rules settle where parts meet (tables.json), and the cells it lies over where it is not the whole table.";
      readonly type: "object";
      readonly properties: {
        readonly name: {
          readonly type: "string";
          readonly minLength: 1;
          readonly maxLength: 200;
        };
        readonly rules: {
          readonly enum: readonly ["word", "excel", "powerpoint"];
        };
        readonly parts: {
          readonly type: "object";
          readonly properties: {
            readonly table: {
              readonly $ref: "#/$defs/part";
            };
            readonly rowBand1: {
              readonly $ref: "#/$defs/part";
            };
            readonly rowBand2: {
              readonly $ref: "#/$defs/part";
            };
            readonly columnBand1: {
              readonly $ref: "#/$defs/part";
            };
            readonly columnBand2: {
              readonly $ref: "#/$defs/part";
            };
            readonly firstColumn: {
              readonly $ref: "#/$defs/part";
            };
            readonly lastColumn: {
              readonly $ref: "#/$defs/part";
            };
            readonly header: {
              readonly $ref: "#/$defs/part";
            };
            readonly totals: {
              readonly $ref: "#/$defs/part";
            };
            readonly topLeft: {
              readonly $ref: "#/$defs/part";
            };
            readonly topRight: {
              readonly $ref: "#/$defs/part";
            };
            readonly bottomLeft: {
              readonly $ref: "#/$defs/part";
            };
            readonly bottomRight: {
              readonly $ref: "#/$defs/part";
            };
          };
          readonly minProperties: 1;
          readonly additionalProperties: false;
        };
        readonly on: {
          readonly type: "object";
          readonly properties: {
            readonly header: {
              readonly type: "boolean";
            };
            readonly totals: {
              readonly type: "boolean";
            };
            readonly firstColumn: {
              readonly type: "boolean";
            };
            readonly lastColumn: {
              readonly type: "boolean";
            };
            readonly rowBands: {
              readonly type: "boolean";
            };
            readonly columnBands: {
              readonly type: "boolean";
            };
          };
          readonly additionalProperties: false;
        };
        readonly bands: {
          readonly type: "object";
          readonly properties: {
            readonly rows: {
              readonly $ref: "#/$defs/bandSizes";
            };
            readonly columns: {
              readonly $ref: "#/$defs/bandSizes";
            };
          };
          readonly minProperties: 1;
          readonly additionalProperties: false;
        };
        readonly lines: {
          readonly $ref: "#/$defs/regionEdges";
        };
        readonly background: {
          readonly anyOf: readonly [{
            readonly $ref: "#/$defs/tint";
          }, {
            readonly type: "object";
            readonly properties: {
              readonly angle: {
                readonly type: "number";
                readonly minimum: 0;
                readonly maximum: 360;
              };
              readonly stops: {
                readonly type: "array";
                readonly items: {
                  readonly type: "object";
                  readonly properties: {
                    readonly at: {
                      readonly type: "number";
                      readonly minimum: 0;
                      readonly maximum: 100;
                    };
                    readonly color: {
                      readonly $ref: "#/$defs/tint";
                    };
                  };
                  readonly required: readonly ["at", "color"];
                  readonly additionalProperties: false;
                };
                readonly minItems: 2;
              };
            };
            readonly required: readonly ["angle", "stops"];
            readonly additionalProperties: false;
          }];
        };
        readonly shadow: {
          readonly description: "In points, its angle in degrees clockwise from the right.";
          readonly type: "object";
          readonly properties: {
            readonly color: {
              readonly $ref: "#/$defs/tint";
            };
            readonly blur: {
              readonly type: "number";
              readonly minimum: 0;
              readonly maximum: 100;
            };
            readonly distance: {
              readonly type: "number";
              readonly minimum: 0;
              readonly maximum: 100;
            };
            readonly angle: {
              readonly type: "number";
              readonly minimum: 0;
              readonly maximum: 360;
            };
          };
          readonly required: readonly ["color", "blur", "distance", "angle"];
          readonly additionalProperties: false;
        };
        readonly spacing: {
          readonly description: "In points.";
          readonly type: "number";
          readonly exclusiveMinimum: 0;
          readonly maximum: 30;
        };
        readonly area: {
          readonly type: "object";
          readonly properties: {
            readonly from: {
              readonly $ref: "#/$defs/cellTo";
            };
            readonly to: {
              readonly $ref: "#/$defs/cellTo";
            };
          };
          readonly required: readonly ["from", "to"];
          readonly additionalProperties: false;
        };
      };
      readonly required: readonly ["rules"];
      readonly additionalProperties: false;
    };
  };
  readonly attrSets: {
    readonly textblock: {
      readonly id: {
        readonly default: null;
        readonly schema: {
          readonly $ref: "#/$defs/id";
        };
      };
      readonly align: {
        readonly default: null;
        readonly schema: {
          readonly $ref: "#/$defs/align";
        };
      };
      readonly indent: {
        readonly default: null;
        readonly schema: {
          readonly $ref: "#/$defs/indent";
        };
      };
      readonly firstLine: {
        readonly default: null;
        readonly schema: {
          readonly description: "Where the first line starts from the others, in cm; negative where it hangs before them.";
          readonly type: "number";
          readonly minimum: -10;
          readonly maximum: 10;
        };
      };
      readonly right: {
        readonly default: null;
        readonly schema: {
          readonly type: "number";
          readonly minimum: 0;
          readonly maximum: 10;
        };
      };
      readonly tabs: {
        readonly default: null;
        readonly schema: {
          readonly type: "array";
          readonly items: {
            readonly $ref: "#/$defs/tabStop";
          };
        };
      };
      readonly style: {
        readonly default: null;
        readonly schema: {
          readonly type: "string";
          readonly pattern: "^[A-Za-z0-9_-]{1,32}$";
        };
      };
      readonly restart: {
        readonly default: false;
        readonly schema: {
          readonly description: "The block's number, of its list or its style, starts again from 1.";
          readonly type: "boolean";
        };
      };
      readonly endMarks: {
        readonly default: null;
        readonly schema: {
          readonly description: "The formatting kept at the paragraph's end, as Word keeps its paragraph mark's.";
          readonly $ref: "#/$defs/marks";
        };
      };
      readonly formatting: {
        readonly default: null;
        readonly schema: {
          readonly description: "A proposed change of the block's type or attributes, with the type and the attributes it had before.";
          readonly type: "object";
          readonly properties: {
            readonly id: {
              readonly $ref: "#/$defs/id";
            };
            readonly author: {
              readonly $ref: "#/$defs/author";
            };
            readonly user: {
              readonly $ref: "#/$defs/user";
            };
            readonly date: {
              readonly $ref: "#/$defs/date";
            };
            readonly before: {
              readonly type: "object";
              readonly properties: {
                readonly type: {
                  readonly type: "string";
                };
                readonly attrs: {
                  readonly type: "object";
                };
              };
              readonly required: readonly ["type", "attrs"];
              readonly additionalProperties: false;
            };
          };
          readonly required: readonly ["id", "author", "before"];
          readonly additionalProperties: false;
        };
      };
    };
    readonly proposed: {
      readonly insertion: {
        readonly default: null;
        readonly schema: {
          readonly description: "The node proposed as inserted; of a paragraph, its end, as Word marks its paragraph mark, so the paragraph's text joins the next paragraph's when the end goes.";
          readonly $ref: "#/$defs/change";
        };
      };
      readonly deletion: {
        readonly default: null;
        readonly schema: {
          readonly description: "The node proposed as deleted; of a paragraph, its end.";
          readonly $ref: "#/$defs/change";
        };
      };
    };
    readonly slide: {
      readonly layout: {
        readonly default: null;
        readonly schema: {
          readonly description: "The id of the template's layout the slide this block starts is laid out by; null chooses one by the slide's content.";
          readonly $ref: "#/$defs/id";
        };
      };
      readonly hidden: {
        readonly default: false;
        readonly schema: {
          readonly description: "The slide this block starts is left out when presenting.";
          readonly type: "boolean";
        };
      };
      readonly background: {
        readonly default: null;
        readonly schema: {
          readonly description: "The background of the slide this block starts, drawn over its layout's as a layout's is (schema/slides.json); null shows its layout's.";
          readonly type: "object";
          readonly properties: {
            readonly color: {
              readonly type: "string";
              readonly pattern: "^#[0-9a-f]{6}$";
            };
            readonly image: {
              readonly type: "string";
              readonly pattern: "^[0-9a-f]{64}$";
            };
          };
          readonly minProperties: 1;
          readonly additionalProperties: false;
        };
      };
    };
  };
  readonly nodes: {
    readonly doc: {
      readonly content: "block+";
    };
    readonly paragraph: {
      readonly group: "block cellblock";
      readonly content: "inline*";
      readonly attrSets: readonly ["textblock", "proposed"];
      readonly attrs: {
        readonly list: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/list";
          };
        };
        readonly checked: {
          readonly default: false;
          readonly schema: {
            readonly type: "boolean";
          };
        };
        readonly continued: {
          readonly default: false;
          readonly schema: {
            readonly description: "The item counts on from its list's last item, across the blocks between them.";
            readonly type: "boolean";
          };
        };
        readonly format: {
          readonly default: null;
          readonly schema: {
            readonly description: "The id of the document's list format the item shows its marker in.";
            readonly $ref: "#/$defs/id";
          };
        };
        readonly speaker: {
          readonly default: false;
          readonly schema: {
            readonly description: "The paragraph is its slide's speaker notes, not on the slide, the page or in Word.";
            readonly type: "boolean";
          };
        };
      };
    };
    readonly title: {
      readonly group: "block cellblock";
      readonly content: "inline*";
      readonly defining: true;
      readonly attrSets: readonly ["textblock", "proposed", "slide"];
    };
    readonly subtitle: {
      readonly group: "block cellblock";
      readonly content: "inline*";
      readonly defining: true;
      readonly attrSets: readonly ["textblock", "proposed"];
    };
    readonly heading: {
      readonly group: "block cellblock";
      readonly content: "inline*";
      readonly defining: true;
      readonly attrSets: readonly ["textblock", "proposed", "slide"];
      readonly attrs: {
        readonly level: {
          readonly default: 1;
          readonly schema: {
            readonly $ref: "#/$defs/level";
          };
        };
      };
    };
    readonly table: {
      readonly group: "block";
      readonly content: "cell*";
      readonly atom: true;
      readonly selectable: true;
      readonly isolating: true;
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly sized: {
          readonly default: false;
          readonly schema: {
            readonly type: "boolean";
          };
        };
        readonly designs: {
          readonly default: null;
          readonly schema: {
            readonly description: "Its designs: one over the whole table, or one over each area of a sheet that Excel keeps as a table.";
            readonly type: "array";
            readonly items: {
              readonly $ref: "#/$defs/design";
            };
            readonly minItems: 1;
          };
        };
        readonly proposedRows: {
          readonly default: null;
          readonly schema: {
            readonly description: "Rows proposed as inserted or deleted, by their ids.";
            readonly type: "object";
            readonly additionalProperties: {
              readonly type: "object";
              readonly properties: {
                readonly insertion: {
                  readonly $ref: "#/$defs/change";
                };
                readonly deletion: {
                  readonly $ref: "#/$defs/change";
                };
              };
              readonly minProperties: 1;
              readonly additionalProperties: false;
            };
          };
        };
        readonly grid: {
          readonly default: null;
          readonly schema: false;
        };
        readonly copied: {
          readonly default: null;
          readonly schema: false;
        };
      };
    };
    readonly cell: {
      readonly content: "cellblock+";
      readonly isolating: true;
      readonly attrs: {
        readonly row: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly col: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly fill: {
          readonly default: null;
          readonly schema: {
            readonly description: "The colour the cell is filled with over its table's design.";
            readonly $ref: "#/$defs/tint";
          };
        };
        readonly edges: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/edges";
          };
        };
      };
    };
    readonly image: {
      readonly group: "block cellblock";
      readonly atom: true;
      readonly selectable: true;
      readonly draggable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly blob: {
          readonly default: null;
          readonly schema: {
            readonly type: "string";
            readonly pattern: "^[0-9a-f]{64}$";
          };
        };
        readonly alt: {
          readonly default: "";
          readonly schema: {
            readonly type: "string";
          };
        };
        readonly width: {
          readonly default: null;
          readonly schema: {
            readonly type: "integer";
            readonly minimum: 5;
            readonly maximum: 100;
          };
        };
        readonly align: {
          readonly default: null;
          readonly schema: {
            readonly enum: readonly ["center", "right"];
          };
        };
      };
    };
    readonly pdf: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly draggable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly blob: {
          readonly default: null;
          readonly schema: {
            readonly type: "string";
            readonly pattern: "^[0-9a-f]{64}$";
          };
        };
        readonly title: {
          readonly default: "";
          readonly schema: {
            readonly type: "string";
            readonly maxLength: 200;
          };
        };
        readonly first: {
          readonly default: null;
          readonly schema: {
            readonly description: "The first of the file's pages the block shows, counted from 1; null from the first.";
            readonly type: "integer";
            readonly minimum: 1;
          };
        };
        readonly last: {
          readonly default: null;
          readonly schema: {
            readonly description: "The last of the file's pages the block shows; null to the last.";
            readonly type: "integer";
            readonly minimum: 1;
          };
        };
        readonly width: {
          readonly default: null;
          readonly schema: {
            readonly type: "integer";
            readonly minimum: 5;
            readonly maximum: 100;
          };
        };
        readonly align: {
          readonly default: null;
          readonly schema: {
            readonly enum: readonly ["center", "right"];
          };
        };
      };
    };
    readonly contents: {
      readonly group: "block cellblock";
      readonly atom: true;
      readonly selectable: true;
      readonly draggable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly depth: {
          readonly default: 3;
          readonly schema: {
            readonly $ref: "#/$defs/level";
          };
        };
      };
    };
    readonly chart: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly draggable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly range: {
          readonly default: null;
          readonly schema: {
            readonly type: "object";
            readonly properties: {
              readonly table: {
                readonly $ref: "#/$defs/id";
              };
              readonly from: {
                readonly $ref: "#/$defs/point";
              };
              readonly to: {
                readonly $ref: "#/$defs/point";
              };
            };
            readonly required: readonly ["table", "from"];
            readonly additionalProperties: false;
          };
        };
        readonly kind: {
          readonly default: "column";
          readonly schema: {
            readonly $ref: "#/$defs/chartKind";
          };
        };
        readonly stacked: {
          readonly default: false;
          readonly schema: {
            readonly type: "boolean";
          };
        };
        readonly by: {
          readonly default: "cols";
          readonly schema: {
            readonly enum: readonly ["rows", "cols"];
          };
        };
        readonly names: {
          readonly default: null;
          readonly schema: {
            readonly type: "boolean";
          };
        };
        readonly labels: {
          readonly default: null;
          readonly schema: {
            readonly type: "boolean";
          };
        };
        readonly title: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/chartTitle";
          };
        };
        readonly legend: {
          readonly default: true;
          readonly schema: {
            readonly type: "boolean";
          };
        };
      };
    };
    readonly horizontalRule: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
      };
    };
    readonly pageBreak: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
      };
    };
    readonly sectionBreak: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
      };
    };
    readonly slideBreak: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly attrSets: readonly ["proposed", "slide"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
      };
    };
    readonly columnBreak: {
      readonly group: "block";
      readonly atom: true;
      readonly selectable: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
      };
    };
    readonly field: {
      readonly group: "inline";
      readonly inline: true;
      readonly atom: true;
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly kind: {
          readonly default: "page";
          readonly schema: {
            readonly $ref: "#/$defs/field";
          };
        };
      };
    };
    readonly footnote: {
      readonly group: "inline";
      readonly inline: true;
      readonly atom: true;
      readonly content: "text*";
      readonly attrSets: readonly ["proposed"];
      readonly attrs: {
        readonly id: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly kind: {
          readonly default: "foot";
          readonly schema: {
            readonly $ref: "#/$defs/note";
          };
        };
      };
    };
    readonly text: {
      readonly group: "inline";
    };
  };
  readonly marks: {
    readonly link: {
      readonly inclusive: false;
      readonly attrs: {
        readonly href: {
          readonly schema: {
            readonly type: "string";
            readonly minLength: 1;
          };
        };
      };
    };
    readonly strong: {};
    readonly em: {};
    readonly underline: {};
    readonly strike: {};
    readonly sub: {
      readonly excludes: "sub sup";
    };
    readonly sup: {
      readonly excludes: "sub sup";
    };
    readonly color: {
      readonly attrs: {
        readonly color: {
          readonly schema: {
            readonly $ref: "#/$defs/color";
          };
        };
      };
    };
    readonly highlight: {
      readonly attrs: {
        readonly color: {
          readonly schema: {
            readonly $ref: "#/$defs/color";
          };
        };
      };
    };
    readonly font: {
      readonly attrs: {
        readonly family: {
          readonly schema: {
            readonly type: "string";
            readonly minLength: 1;
          };
        };
      };
    };
    readonly size: {
      readonly attrs: {
        readonly pt: {
          readonly schema: {
            readonly type: "number";
            readonly minimum: 1;
            readonly maximum: 400;
          };
        };
      };
    };
    readonly kerning: {
      readonly attrs: {
        readonly on: {
          readonly schema: {
            readonly type: "boolean";
          };
        };
      };
    };
    readonly insertion: {
      readonly inclusive: false;
      readonly attrs: {
        readonly id: {
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly author: {
          readonly schema: {
            readonly $ref: "#/$defs/author";
          };
        };
        readonly user: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/user";
          };
        };
        readonly date: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/date";
          };
        };
      };
    };
    readonly deletion: {
      readonly inclusive: false;
      readonly attrs: {
        readonly id: {
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly author: {
          readonly schema: {
            readonly $ref: "#/$defs/author";
          };
        };
        readonly user: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/user";
          };
        };
        readonly date: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/date";
          };
        };
      };
    };
    readonly formatting: {
      readonly inclusive: false;
      readonly attrs: {
        readonly id: {
          readonly schema: {
            readonly $ref: "#/$defs/id";
          };
        };
        readonly author: {
          readonly schema: {
            readonly $ref: "#/$defs/author";
          };
        };
        readonly user: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/user";
          };
        };
        readonly date: {
          readonly default: null;
          readonly schema: {
            readonly $ref: "#/$defs/date";
          };
        };
        readonly before: {
          readonly schema: {
            readonly description: "The text's formatting before the proposed change.";
            readonly $ref: "#/$defs/marks";
          };
        };
      };
    };
  };
};
export default schema;
