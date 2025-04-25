// CodeMirror, copyright (c) by Marijn Haverbeke and others
// Distributed under an MIT license: https://codemirror.net/LICENSE
// Modified for Modsec by Roxy-WI
(function(mod) {
  if (typeof exports == "object" && typeof module == "object") // CommonJS
    mod(require("../../lib/codemirror"));
  else if (typeof define == "function" && define.amd) // AMD
    define(["../../lib/codemirror"], mod);
  else // Plain browser env
    mod(CodeMirror);
})(function(CodeMirror) {
"use strict";
CodeMirror.defineMode("modsec", function(config) {
  function words(str) {
    var obj = {}, words = str.split(" ");
    for (var i = 0; i < words.length; ++i) obj[words[i]] = true;
    return obj;
  }

  const keywords = words(
      "SecRule SecAction SecMarker SecRequestBodyAccess SecResponseBodyAccess " +
      "SecDefaultAction SecDebugLog SecRuleEngine SecAuditLog"
  );

  const operators = words(
      "eq ge gt le lt ne rx streq contains inspectFile validateByteRange " +
      "validateUrlEncoding validateUtf8Encoding inspectSignature ipMatch ipMatchFromFile rsub rbl pm pmFromFile validateNidsPayload ranges md5"
  );

  const flags = words(
      "deny allow log skip chain redirect pass tag ctl capture auditlog id " +
      "severity msg phase skipAfter status t transform persistBlock exec resetConnection pause intercept replace removeTag setvar expirevar drop"
  );

  const actions = words(
      "id msg rev severity accuracy maturity skipAfter logdata t chain capture deny block allow ctl tag ver ipMatch pm isBase64Decode status transform nxssDecode compress"
  );

  var indentUnit = config.indentUnit, type;

  function ret(style, tp) {
    type = tp;
    return style;
  }

  function tokenBase(stream, state) {
    stream.eatWhile(/[\w\$_]/);
    var cur = stream.current();
    if (keywords.propertyIsEnumerable(cur)) {
      return ret("keyword", "keyword"); // Основные директивы
    } else if (operators.propertyIsEnumerable(cur)) {
      return ret("operator", "operator"); // Операторы
    } else if (flags.propertyIsEnumerable(cur)) {
      return ret("attribute", "flag"); // Флаги
    } else if (actions.propertyIsEnumerable(cur)) {
      return ret("variable-2", "action"); // Действия
    }

    var ch = stream.next();
    if (ch == "@") {
      stream.eatWhile(/[\w\\\-]/);
      return ret("meta", stream.current());
    } else if (ch == "/" && stream.eat("*")) {
      state.tokenize = tokenCComment;
      return tokenCComment(stream, state);
    } else if (ch == "<" && stream.eat("!")) {
      state.tokenize = tokenSGMLComment;
      return tokenSGMLComment(stream, state);
    } else if (ch == "=") ret(null, "compare");
    else if ((ch == "~" || ch == "|") && stream.eat("=")) return ret(null, "compare");
    else if (ch == "\"" || ch == "'") {
      state.tokenize = tokenString(ch);
      return state.tokenize(stream, state);
    } else if (ch == "#") {
      stream.skipToEnd();
      return ret("comment", "comment");
    } else if (ch == "!") {
      stream.match(/^\s*\w*/);
      return ret("keyword", "important");
    } else if (/\d/.test(ch)) {
      stream.eatWhile(/[\w.%]/);
      return ret("number", "unit");
    } else if (/[,.+>*\/]/.test(ch)) {
      return ret(null, "select-op");
    } else if (/[;{}:\[\]]/.test(ch)) {
      return ret(null, ch);
    } else {
      stream.eatWhile(/[\w\\\-]/);
      return ret("variable", "variable");
    }
  }

  function tokenCComment(stream, state) {
    var maybeEnd = false, ch;
    while ((ch = stream.next()) != null) {
      if (maybeEnd && ch == "/") {
        state.tokenize = tokenBase;
        break;
      }
      maybeEnd = (ch == "*");
    }
    return ret("comment", "comment");
  }

  function tokenSGMLComment(stream, state) {
    var dashes = 0, ch;
    while ((ch = stream.next()) != null) {
      if (dashes >= 2 && ch == ">") {
        state.tokenize = tokenBase;
        break;
      }
      dashes = (ch == "-") ? dashes + 1 : 0;
    }
    return ret("comment", "comment");
  }

  function tokenString(quote) {
    return function (stream, state) {
      var escaped = false, ch;
      while ((ch = stream.next()) != null) {
        if (ch == quote && !escaped)
          break;
        escaped = !escaped && ch == "\\";
      }
      if (!escaped) state.tokenize = tokenBase;
      return ret("string", "string");
    };
  }

  return {
    startState: function (base) {
      return {
        tokenize: tokenBase,
        baseIndent: base || 0,
        stack: []
      };
    },
    token: function (stream, state) {
      if (stream.eatSpace()) return null;
      type = null;
      var style = state.tokenize(stream, state);

      var context = state.stack[state.stack.length - 1];
      if (type == "hash" && context == "rule") style = "atom";
      else if (style == "variable") {
        if (context == "rule") style = "number";
        else if (!context || context == "@media{") style = "tag";
      }
      if (context == "rule" && /^[\{\};]$/.test(type))
        state.stack.pop();
      if (type == "{") {
        if (context == "@media") state.stack[state.stack.length - 1] = "@media{";
        else state.stack.push("{");
      } else if (type == "}") state.stack.pop();
      else if (type == "@media") state.stack.push("@media");
      else if (context == "{" && type != "comment") state.stack.push("rule");
      return style;
    },
    indent: function (state, textAfter) {
      var n = state.stack.length;
      if (/^\}/.test(textAfter))
        n -= state.stack[state.stack.length - 1] == "rule" ? 2 : 1;
      return state.baseIndent + n * indentUnit;
    },

    electricChars: "}",
    lineComment: "#"
  };
});
CodeMirror.defineMIME("text/x-modsec-conf", "modsec");
});
