#include <stdio.h>

/* Reference implementation for add_two_integers.
 * Reads the operands into a 64-bit type and adds in 64-bit, so it never
 * invokes signed overflow (U-07 wider-type contract). */
int main(void) {
    long long a, b;
    if (scanf("%lld %lld", &a, &b) != 2) {
        return 1;
    }
    printf("%lld\n", a + b);
    return 0;
}
