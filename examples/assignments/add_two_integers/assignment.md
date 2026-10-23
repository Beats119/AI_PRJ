# Add Two Integers

## Problem

Read two integers on a single line separated by whitespace and print their
sum followed by a newline.

## Input

A single line containing two integers separated by whitespace. Each operand
is a signed 32-bit integer (INT_MIN to INT_MAX).

## Output

A single line containing the mathematically correct sum of the two operands,
followed by a newline. The sum of two signed 32-bit integers always fits in
a signed 64-bit integer; the correct sum must be printed even when it lies
outside the signed 32-bit range.

## Constraints

- Each operand is in the signed 32-bit range [-2147483648, 2147483647].
- The required output is the mathematically correct sum (wider-type contract).

## Boundary

- Both operands at the minimum / maximum of the supported range.
- Zero, negative, and mixed-sign operands.
