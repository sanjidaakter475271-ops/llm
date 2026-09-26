/**
 * BAF Letter Generator v3
 * =======================
 * Fixes:
 * - Header block and signature block properly right-aligned
 * - Empty fields are skipped cleanly
 * - No duplicate classification in body (header/footer only)
 */

const {
  Document, Packer, Paragraph, TextRun, AlignmentType,
  UnderlineType, convertInchesToTwip, TabStopType,
  Header, Footer
} = require('docx');
const fs = require('fs');

// ── FORMATTING CONFIG ────────────────────────────────────────────
const CONFIG = {
  font: {
    main: 'Times New Roman',
    size: 24,   // 12pt
  },
  page: {
    marginTop:    convertInchesToTwip(1.0),
    marginBottom: convertInchesToTwip(1.0),
    marginLeft:   convertInchesToTwip(1.25),
    marginRight:  convertInchesToTwip(1.25),
  },
  spacing: {
    afterPara:   200,
    afterSmall:   80,
    afterTiny:    40,
    lineSpacing: 276,
  },
  indent: {
    paraText:    720,
    subPara:     720,
    subText:    1440,
    blockIndent: 4680,   // left indent for header/signature block (~3.25in from left margin)
  }
};
// ────────────────────────────────────────────────────────────────


// ── HELPERS ─────────────────────────────────────────────────────

function txt(text, opts = {}) {
  return new TextRun({
    text: String(text || ''),
    font: CONFIG.font.main,
    size: opts.size || CONFIG.font.size,
    bold: opts.bold || false,
    underline: opts.underline ? { type: UnderlineType.SINGLE } : undefined,
  });
}

function para(runs, opts = {}) {
  return new Paragraph({
    children: Array.isArray(runs) ? runs : [runs],
    alignment: opts.align || AlignmentType.LEFT,
    spacing: {
      before: opts.spaceBefore || 0,
      after:  opts.spaceAfter !== undefined ? opts.spaceAfter : CONFIG.spacing.afterPara,
      line:   CONFIG.spacing.lineSpacing,
    },
    indent: opts.indent ? { left: opts.indent } : undefined,
    tabStops: opts.tabStops || [],
  });
}

function emptyLine() {
  return para(txt(''), { spaceAfter: 0 });
}

// Header/signature block line — fixed LEFT indent (matches real JSSDM letters,
// where the block starts at a fixed tab position and is left-aligned within it,
// NOT flush to the page's right margin).
function rightPara(text, opts = {}) {
  return new Paragraph({
    children: [txt(text, opts)],
    alignment: AlignmentType.LEFT,
    indent: { left: CONFIG.indent.blockIndent },
    spacing: {
      before: 0,
      after: opts.spaceAfter !== undefined ? opts.spaceAfter : CONFIG.spacing.afterSmall,
      line: CONFIG.spacing.lineSpacing,
    },
  });
}

function subjectLine(text) {
  return para(txt(text, { bold: true, underline: true }), {
    spaceAfter: CONFIG.spacing.afterPara,
  });
}

function refLine(letter, text) {
  return para([txt(letter + '.'), new TextRun({ text: '\t', font: CONFIG.font.main, size: CONFIG.font.size }), txt(text)], {
    tabStops: [{ type: TabStopType.LEFT, position: CONFIG.indent.paraText }],
    spaceAfter: CONFIG.spacing.afterTiny,
  });
}

function bodyPara(num, text) {
  return para([
    txt(num + '.'),
    new TextRun({ text: '\t', font: CONFIG.font.main, size: CONFIG.font.size }),
    txt(text),
  ], {
    tabStops: [{ type: TabStopType.LEFT, position: CONFIG.indent.paraText }],
    spaceAfter: CONFIG.spacing.afterPara,
  });
}

function subPara(letter, text) {
  return para([
    txt(letter + '.'),
    new TextRun({ text: '\t', font: CONFIG.font.main, size: CONFIG.font.size }),
    txt(text),
  ], {
    indent: CONFIG.indent.subPara,
    tabStops: [{ type: TabStopType.LEFT, position: CONFIG.indent.subText }],
    spaceAfter: CONFIG.spacing.afterTiny,
  });
}

// Distribution — all flush left
function distrSection(extlAct, extlInfo, intlAct, intlInfo) {
  const lines = [];
  const sp = CONFIG.spacing.afterTiny;

  lines.push(para(txt('Distr:'), { spaceAfter: sp }));
  lines.push(para(txt('Extl:'),  { spaceAfter: sp }));

  if (extlAct && extlAct.length) {
    lines.push(para(txt('Act:'), { spaceAfter: sp }));
    extlAct.forEach(a => lines.push(para(txt(a), { spaceAfter: sp })));
  }
  if (extlInfo && extlInfo.length) {
    lines.push(para(txt('Info:'), { spaceAfter: sp }));
    extlInfo.forEach(a => lines.push(para(txt(a), { spaceAfter: sp })));
  }
  if ((intlAct && intlAct.length) || (intlInfo && intlInfo.length)) {
    lines.push(para(txt('Internal:'), { spaceAfter: sp }));
    if (intlAct && intlAct.length) {
      lines.push(para(txt('Act:'), { spaceAfter: sp }));
      intlAct.forEach(a => lines.push(para(txt(a), { spaceAfter: sp })));
    }
    if (intlInfo && intlInfo.length) {
      lines.push(para(txt('Info:'), { spaceAfter: sp }));
      intlInfo.forEach(a => lines.push(para(txt(a), { spaceAfter: sp })));
    }
  }
  return lines;
}

function buildBody(bodyArr) {
  const lines = [];
  if (!bodyArr || !bodyArr.length) return lines;
  bodyArr.forEach((b, i) => {
    if (typeof b === 'string') {
      lines.push(bodyPara(i + 1, b));
    } else if (b && b.text) {
      lines.push(bodyPara(i + 1, b.text));
      if (b.subItems && b.subItems.length) {
        b.subItems.forEach((sub, si) =>
          lines.push(subPara(String.fromCharCode(97 + si), sub))
        );
      }
    }
  });
  return lines;
}

// File ref left, date aligned under the header block (same column as Tel/Email)
function fileRefLine(fileRef, date) {
  return para([
    txt(fileRef || ''),
    new TextRun({ text: '\t', font: CONFIG.font.main, size: CONFIG.font.size }),
    txt(date || ''),
  ], {
    tabStops: [{ type: TabStopType.LEFT, position: CONFIG.indent.blockIndent }],
    spaceAfter: CONFIG.spacing.afterPara,
  });
}

// Header and footer with classification on every page
function makeHeaderFooter(classification) {
  const classText = (classification || 'RESTRICTED').toUpperCase();
  return {
    header: new Header({
      children: [new Paragraph({
        children: [new TextRun({ text: classText, font: CONFIG.font.main, size: CONFIG.font.size, bold: true })],
        alignment: AlignmentType.CENTER,
        spacing: { after: 40 },
      })]
    }),
    footer: new Footer({
      children: [new Paragraph({
        children: [new TextRun({ text: classText, font: CONFIG.font.main, size: CONFIG.font.size, bold: true })],
        alignment: AlignmentType.CENTER,
        spacing: { before: 40 },
      })]
    }),
  };
}


// ── LETTER BUILDERS ──────────────────────────────────────────────

function buildRoutineLetter(d) {
  const c = [];

  // Priority — centered, only if provided
  if (d.priority && d.priority.trim()) {
    c.push(para(txt(d.priority.trim(), { bold: true }), {
      align: AlignmentType.CENTER,
      spaceAfter: CONFIG.spacing.afterSmall,
    }));
    c.push(emptyLine());
  }

  // Header block — right aligned using tab trick
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  if (d.dte)     c.push(rightPara(d.dte));
  if (d.address) c.push(rightPara(d.address));
  c.push(emptyLine());
  if (d.tel)     c.push(rightPara('Tel: ' + d.tel));
  if (d.email)   c.push(rightPara('Email: ' + d.email));
  c.push(emptyLine());

  // File ref + date
  c.push(fileRefLine(d.fileRef, d.date));

  // Subject
  c.push(subjectLine(d.subject));

  // References — only if refs array is non-empty
  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  // Body
  c.push(...buildBody(d.body));
  c.push(emptyLine());

  // Signature — right aligned using tab trick
  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  if (d.sigFor)  c.push(rightPara('For ' + d.sigFor));
  c.push(emptyLine());

  // Distribution
  c.push(...distrSection(d.extlAct, d.extlInfo, d.intlAct, d.intlInfo));

  return c;
}

function buildLooseMinute(d) {
  const c = [];

  if (d.branch) c.push(para(txt(d.branch, { underline: true }), { align: AlignmentType.CENTER, spaceAfter: 20 }));
  if (d.dte)    c.push(para(txt('(' + d.dte + ')'), { align: AlignmentType.CENTER, spaceAfter: CONFIG.spacing.afterSmall }));
  if (d.priority && d.priority.trim()) {
    c.push(para(txt(d.priority.trim(), { bold: true }), { spaceAfter: CONFIG.spacing.afterSmall }));
  }
  c.push(para(txt('LM'), { spaceAfter: CONFIG.spacing.afterSmall }));
  if (d.lmRef) c.push(para(txt(d.lmRef), { spaceAfter: CONFIG.spacing.afterSmall }));
  c.push(subjectLine(d.subject));

  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  c.push(...buildBody(d.body));
  c.push(emptyLine());

  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  if (d.ext)     c.push(rightPara('Ext: ' + d.ext));
  if (d.date)    c.push(rightPara(d.date));
  c.push(emptyLine());

  c.push(para(txt('To:'), { spaceAfter: CONFIG.spacing.afterTiny }));
  if (d.to) d.to.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  c.push(emptyLine());
  if (d.info && d.info.length) {
    c.push(para(txt('Info:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.info.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  }

  return c;
}

function buildDirectedLetter(d) {
  const c = [];
  c.push(emptyLine());
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  if (d.dte)     c.push(rightPara(d.dte));
  if (d.address) c.push(rightPara(d.address));
  c.push(emptyLine());
  if (d.tel)     c.push(rightPara('Tel: ' + d.tel));
  if (d.email)   c.push(rightPara('Email: ' + d.email));
  c.push(emptyLine());
  c.push(fileRefLine(d.fileRef, d.date));
  c.push(subjectLine(d.subject));

  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  c.push(...buildBody(d.body));
  c.push(emptyLine());
  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  if (d.sigFor)  c.push(rightPara('For ' + d.sigFor));
  c.push(emptyLine());
  c.push(para(txt('To:'), { spaceAfter: CONFIG.spacing.afterTiny }));
  if (d.to) d.to.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  return c;
}


function buildFormalLetter(d) {
  const c = [];
  if (d.priority && d.priority.trim()) {
    c.push(para(txt(d.priority.trim(), { bold: true }), { align: AlignmentType.CENTER, spaceAfter: CONFIG.spacing.afterSmall }));
  }
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  if (d.dte)     c.push(rightPara(d.dte));
  if (d.address) c.push(rightPara(d.address));
  c.push(emptyLine());
  if (d.tel)     c.push(rightPara('Tel: ' + d.tel));
  if (d.email)   c.push(rightPara('Email: ' + d.email));
  c.push(emptyLine());
  c.push(fileRefLine(d.fileRef, d.date));
  
  if (d.to && d.to.length) {
    c.push(para(txt('To:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.to.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
    c.push(emptyLine());
  }

  c.push(subjectLine(d.subject));

  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  c.push(...buildBody(d.body));
  c.push(emptyLine());

  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  if (d.sigFor)  c.push(rightPara('For ' + d.sigFor));
  c.push(emptyLine());

  if (d.info && d.info.length) {
    c.push(para(txt('Info:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.info.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  }

  return c;
}

function buildDemiOfficial(d) {
  const c = [];
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  if (d.address) c.push(rightPara(d.address));
  if (d.tel)     c.push(rightPara('Tel: ' + d.tel));
  c.push(emptyLine());
  c.push(fileRefLine(d.fileRef, d.date));

  c.push(para(txt('Dear ' + (d.salutation || 'Sir,'), { bold: true }), { spaceAfter: CONFIG.spacing.afterPara }));

  if (d.subject) c.push(subjectLine(d.subject));

  c.push(...buildBody(d.body));
  c.push(emptyLine());

  c.push(rightPara('Yours sincerely,', { spaceAfter: CONFIG.spacing.afterPara }));
  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  c.push(emptyLine());

  if (d.to && d.to.length) {
    d.to.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  }

  return c;
}

function buildCommandedLetter(d) {
  const c = [];
  if (d.priority && d.priority.trim()) {
    c.push(para(txt(d.priority.trim(), { bold: true }), { align: AlignmentType.CENTER, spaceAfter: CONFIG.spacing.afterSmall }));
  }
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  if (d.dte)     c.push(rightPara(d.dte));
  if (d.address) c.push(rightPara(d.address));
  c.push(emptyLine());
  c.push(fileRefLine(d.fileRef, d.date));

  c.push(subjectLine(d.subject));

  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  c.push(...buildBody(d.body));
  c.push(emptyLine());

  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  c.push(emptyLine());

  c.push(...distrSection(d.extlAct, d.extlInfo, d.intlAct, d.intlInfo));

  return c;
}

function buildMemorandum(d) {
  const c = [];
  c.push(para(txt('MEMORANDUM', { bold: true, underline: true }), { align: AlignmentType.CENTER, spaceAfter: CONFIG.spacing.afterPara }));
  if (d.unit)    c.push(rightPara(d.unit));
  if (d.branch)  c.push(rightPara(d.branch));
  c.push(emptyLine());
  c.push(fileRefLine(d.fileRef, d.date));

  c.push(subjectLine(d.subject));

  if (d.refs && d.refs.length > 0) {
    c.push(para(txt(d.refs.length === 1 ? 'Ref:' : 'Refs:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.refs.forEach((r, i) => c.push(refLine(String.fromCharCode(65 + i), r)));
    c.push(emptyLine());
  }

  c.push(...buildBody(d.body));
  c.push(emptyLine());

  if (d.sigName) c.push(rightPara(d.sigName, { bold: true }));
  if (d.sigRank) c.push(rightPara(d.sigRank));
  if (d.sigAppt) c.push(rightPara(d.sigAppt));
  c.push(emptyLine());

  if (d.to && d.to.length) {
    c.push(para(txt('To:'), { spaceAfter: CONFIG.spacing.afterTiny }));
    d.to.forEach(t => c.push(para(txt(t), { spaceAfter: CONFIG.spacing.afterTiny })));
  }

  return c;
}

// ── MAIN ─────────────────────────────────────────────────────────

function buildDocument(d) {
  let children;
  switch (d.type) {
    case 'lm':  children = buildLooseMinute(d);    break;
    case 'dl':  children = buildDirectedLetter(d); break;
    case 'fl':  children = buildFormalLetter(d);   break;
    case 'do':  children = buildDemiOfficial(d);   break;
    case 'cl':  children = buildCommandedLetter(d); break;
    case 'mem': children = buildMemorandum(d);     break;
    default:    children = buildRoutineLetter(d);  break;
  }

  const { header, footer } = makeHeaderFooter(d.classification);

  return new Document({
    sections: [{
      headers: { default: header },
      footers: { default: footer },
      properties: {
        page: {
          margin: {
            top:    CONFIG.page.marginTop,
            bottom: CONFIG.page.marginBottom,
            left:   CONFIG.page.marginLeft,
            right:  CONFIG.page.marginRight,
            header: convertInchesToTwip(0.4),
            footer: convertInchesToTwip(0.4),
          }
        }
      },
      children,
    }],
  });
}

const dataFile = process.argv[2];
const outFile  = process.argv[3] || 'output_letter.docx';
if (!dataFile) { console.error('Usage: node generate_letter.js <data.json> <output.docx>'); process.exit(1); }

const letterData = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
Packer.toBuffer(buildDocument(letterData)).then(buf => {
  fs.writeFileSync(outFile, buf);
  console.log('✅ Generated: ' + outFile);
}).catch(err => { console.error('❌', err.message); process.exit(1); });
