# Ask Mode Design Philosophy

Ask mode is designed around **maximal permissiveness**: always try to do something meaningful with whatever the child types. This document explains how the evaluator thinks about expressions.

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
cat * 5         → 🐱🐱🐱🐱🐱 (with label: "5 cats")
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
3 * 4 + 2 dogs        → "14 dogs"
                        🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶🐶

12 * 3 cats           → "36 cats"
                        🐱🐱🐱🐱... (36 cats)
```

But simple expressions don't need labels:
```
3 cats                → 🐱🐱🐱 (no label, obvious)
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

When the result isn't obvious from the input, show the count. `3 * 4 + 2 dogs` needs the "14 dogs" label because a child can't easily compute that. But `3 cats` doesn't need a label because it's visually obvious.

### Why Spaces Between Emoji Types?

`🐱🐶` is harder to parse visually than `🐱 🐶`. Spaces help kids see "this is a cat AND a dog" rather than "this is one thing".

---

## Implementation Notes

The evaluator tries methods in order:
1. Parentheses (recursive evaluation)
2. Plus expressions (with color mixing, emoji handling)
3. Multiplication expressions
4. Pure math
5. Text substitution (emoji replacement in sentences)

Each method can "pass through" to the next if it doesn't fully handle the input. This layered approach allows complex expressions to be evaluated piece by piece.

---

💜
