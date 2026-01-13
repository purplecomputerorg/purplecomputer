# Explore Mode Design Philosophy

Explore mode is designed around **maximal permissiveness**: always try to do something meaningful with whatever the child types. This document explains how the evaluator thinks about expressions.

---

## Core Principle

**Be like a kind teacher, not a strict compiler.** If a 5-year-old types something, find a way to make it work. Never show errors. Always produce a visual result when possible.

---

## Expression Types

### Pure Math
Standard arithmetic with operator precedence preserved:

```
2 + 2           → 4 (with dot visualization: ••••)
3 * 4 + 2       → 14 (multiplication before addition)
(2 + 3) * 4     → 20 (parentheses override precedence)
10 / 2          → 5
```

### Emoji Expressions
Words become emojis. Supports multiplication and addition:

```
cat             → 🐱
3 cats          → 🐱🐱🐱
cat * 5         → 5 🐱
                  🐱🐱🐱🐱🐱
cats            → 🐱🐱 (bare plural = 2)
cat + dog       → 🐱 🐶 (space between different types)
cat + cat       → 🐱🐱 (no space, same type)
```

### Color Mixing
Colors mix like paint (subtractive mixing):

```
red + blue      → purple (big swatch display)
red + yellow    → orange
3 red + 2 blue  → weighted mix toward red
```

### Mixed Expressions
Emojis, colors, numbers, and text can all combine:

```
apple + red + green   → Line 1: 🍎 [red] [green] (inputs)
                        Line 2: 🍎 [mixed] (result)

3 + 4 + 2 bananas     → 9 bananas
                        🍌🍌🍌🍌🍌🍌🍌🍌🍌

gibberish + blue      → gibberish [blue swatch]
```

---

## Key Behaviors

### Numbers Attach to Next Emoji
When numbers appear before emojis in a + expression, they accumulate and attach:

```
3 + 4 + 2 bananas     → 9 bananas (3+4+2=9, then attach to bananas)
5 + 2 cats + 3 dogs   → 7 cats + 3 dogs (5+2=7 cats, 3 dogs separate)
```

### Operator Precedence Preserved
Math operators follow standard precedence, even with emojis:

```
3 * 4 + 2 dogs        → 14 dogs (3*4=12, +2=14)
2 + 3 * 4 cats        → 14 cats (3*4=12, +2=14)
(2 + 3) * 4 cats      → 20 cats (parentheses first)
```

### Labels for Computed Expressions
When computation happens, show the count to help kids understand:

```
3 * 4 + 2 dogs        → 14 🐶
                        🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶

12 * 3 cats           → 36 🐱
                        🐱🐱🐱🐱... (36 cats)

(cat * 3) + 2         → 5 🐱
                        🐱🐱🐱🐱🐱

(2 * 3) cats          → 6 🐱
                        🐱🐱🐱🐱🐱🐱
```

Parentheses imply computation, so they always show labels:
```
(2 + 2) cats          → 4 🐱
                        🐱🐱🐱🐱

what is (3 * 2) dogs  → what is 6 🐶
                        what is 🐶🐶🐶🐶🐶🐶
```

But simple expressions don't need labels:
```
3 cats                → 🐱🐱🐱 (no label, obvious)
6 cats                → 🐱🐱🐱🐱🐱🐱 (no label, no computation)
cat                   → 🐱
```

### Spaces Between Different Emoji Types
Visual clarity for kids:

```
cat + dog             → 🐱 🐶 (space between)
2 cats + 3 dogs       → 🐱🐱 🐶🐶🐶 (space between groups)
3 cats                → 🐱🐱🐱 (no space, same type)
```

### Colors Mix Even with Non-Colors Between
All colors in an expression mix together:

```
red + cat + blue      → Cat appears, colors mix to purple
apple + red + green   → Apple appears, colors mix
```

### Unknown Text Passes Through
Text that isn't recognized still appears, with valid terms processed:

```
my name is tavi apple → my name is tavi 🍎
gibberish + blue      → gibberish [blue swatch]
```

### Text with Expressions
When English text precedes an expression, the text is preserved:

```
what is 2 + 3         → what is 5
                        what is •••••

I have 5 apples       → I have 🍎🍎🍎🍎🍎

I have 2 + 3 apples   → I have 5 🍎
                        I have 🍎🍎🍎🍎🍎

what is red + blue    → what is [color result]

show me 3 cats        → show me 🐱🐱🐱
```

The prefix must be plain English text (no emojis, numbers, or operators). This allows natural questions like "what is 2 + 2" to work intuitively.

---

## Multiplication Operators

All of these mean the same thing:
- `*` (asterisk)
- `x` (letter x between numbers/words)
- `times` (word)

```
3 * cat               → 🐱🐱🐱
3 x cat               → 🐱🐱🐱
3 times cat           → 🐱🐱🐱
cat times 3           → 🐱🐱🐱
5 x 2 cats            → 10 cats (5*2=10)
```

---

## Autocomplete

Autocomplete helps kids discover words:

- **Triggers at 2+ characters** (e.g., "ca" suggests "cat")
- **Common 2-letter words are excluded** to prevent unwanted completions
  - Excluded: am, an, as, at, be, by, do, go, he, if, in, is, it, me, my, no, of, on, or, so, to, up, us, we, hi, oh, ok
- **Space accepts** the current suggestion
- **Exact matches don't show suggestions** (typing "cat" doesn't suggest "cat")

---

## Display Rules

### Arrows on Every Line
All output lines get the → prefix for visual consistency.

### Two-Line Color+Emoji Display
When colors mix with emojis, show inputs then result:

```
Ask: apple + red + green
  → 🍎 [red] [green]    (what you typed)
  → 🍎 [mixed]          (what you get)
```

### Dot Visualization for Numbers
Small numbers (1-999) show dots below:

```
Ask: 5
  → 5
  → •••••
```

---

## Design Rationale

### Why Maximal Permissiveness?

1. **No error messages.** A 4-year-old shouldn't see "syntax error". If they type something, show them something.

2. **Intuitive over correct.** `3 + 4 + 2 bananas` becoming `9 bananas` is what a child expects, even if it's not mathematically rigorous.

3. **Discovery through play.** Kids learn what works by trying things. Permissive evaluation rewards experimentation.

4. **Visual feedback always.** Even "gibberish + blue" shows the blue. There's always something to see.

### Why Preserve Operator Precedence?

Kids will eventually learn real math. Better to teach them correctly from the start. `3 * 4 + 2 = 14`, not 18.

### Why Labels on Computed Expressions?

When the result isn't obvious from the input, show the count. `3 * 4 + 2 dogs` needs the "14 🐶" label because a child can't easily compute that. But `3 cats` doesn't need a label because it's visually obvious.

Parentheses always trigger labels because they imply computation happened, even if the final expression looks simple. `(2 * 3) cats` becomes `6 cats` after paren evaluation, but we show `6 🐱` as a label because the child typed a computation.

### Why Spaces Between Emoji Types?

`🐱🐶` is harder to parse visually than `🐱 🐶`. Spaces help kids see "this is a cat AND a dog" rather than "this is one thing".

---

## Speech

Add `!` anywhere in your input to hear it spoken aloud using Piper TTS. The `!` is stripped before display and evaluation.

### Triggers

| Method | Example | Notes |
|--------|---------|-------|
| `!` anywhere | `cat!`, `!2+2`, `ca!t` | Most intuitive for kids |
| `say` or `talk` prefix | `say cat`, `talk 2+2` | Alternative syntax |
| Enter on empty | (press Enter after a result) | "Say it again" |

### Principles

1. **Say minimal text.** Don't pronounce emoji symbols or color boxes.
2. **For computation:** Say "input equals result"
3. **For simple lookups:** Just say the word

### Examples

```
cat!                  → shows 🐱, says "cat"
3 cats!               → shows 🐱🐱🐱, says "3 cats"
cat * 3!              → shows result, says "cat times 3 equals 3 cats"
2 + 3 apples!         → says "2 plus 3 apples equals 5 apples"
red + blue!           → says "red plus blue equals purple"
what is 2 + 3!        → says "what is 2 plus 3 equals 5"
```

After any result, pressing Enter with empty input repeats the last spoken result. This is the "what did it say?" feature for kids who want to hear it again.

### Operators in Speech

- `*` → "times"
- `+` → "plus"
- `-` → "minus"
- `/` → "divided by"
- Parentheses are removed

---

## Number Attachment Rules

Numbers attach to the **next term** (color or emoji). They accumulate until they hit something.

```
2 + 3 yellow          → 5 yellows (2+3=5 attaches to yellow)
2 + red               → 3 reds (2+1=3)
3 + 4 + 2 bananas     → 9 bananas (3+4+2=9 attaches to bananas)
2 + red + 3 cats      → 3 reds + 3 cats (2→red, 3→cats)
```

Colors still mix together regardless of where they appear in the expression.

---

## Overlapping Words (Color + Emoji)

Some words are both colors and emojis (e.g., "orange", "peach", "rose"). The behavior is context-sensitive:

### Standalone: Emoji Priority
```
orange                → 🍊 (fruit emoji)
peach                 → 🍑 (fruit emoji)
3 orange              → 🍊🍊🍊 (emoji multiplication)
```

### In + Expressions: Color Priority
```
orange + blue         → color mix (greenish-brown)
2 + 3 orange          → 5 oranges for color mixing
```

### Autocomplete Shows Both
When typing "ora", autocomplete shows overlapping words grouped together:
```
orange 🍊 ██
```
The emoji appears first, then the color swatch. This helps kids see both options exist for words like "orange", "peach", and "rose".

---

## Implementation Notes

The evaluator tries methods in order:
1. Parentheses (recursive evaluation)
2. Text with expression (e.g., "what is 2 + 3")
3. Plus expressions (with color mixing, emoji handling)
4. Multiplication expressions
5. Pure math
6. Text substitution (emoji replacement in sentences)

Each method can "pass through" to the next if it doesn't fully handle the input. This layered approach allows complex expressions to be evaluated piece by piece.

### Operator Constants
Math operators are defined centrally in `SimpleEvaluator`:
- `MATH_SYMBOLS`: `{'+', '-', '*', '/', '×', '÷', '−'}`
- `WORD_TO_SYMBOL`: `{'times': '*', 'plus': '+', 'minus': '-', 'x': '*'}`
- `PLUS_PATTERN`: regex for detecting + or "plus"
- `MATH_CHARS_PATTERN`: regex for valid math expression characters

---

💜
