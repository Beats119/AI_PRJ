#include <stdio.h>

/* The PDF's worked-example submission: everything in main, 32-bit ints.
 * Fails on large operands: INT_MAX + 1 is signed overflow (undefined
 * behaviour), and even where it wraps it is not the mathematically
 * correct sum the assignment requires. */
int main(void) {
    int a, b;
    scanf("%d %d", &a, &b);
    printf("%d\n", a + b);
    return 0;
}
