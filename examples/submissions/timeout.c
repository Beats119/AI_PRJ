#include <stdio.h>

/* Reads the input, then never terminates: the workflow's smoke run must
 * catch this and mark it suspected_infinite_loop. */
int main(void) {
    long long a, b;
    if (scanf("%lld %lld", &a, &b) != 2) {
        return 1;
    }
    for (;;) {
        /* busy-wait forever */
    }
    printf("%lld\n", a + b);
    return 0;
}
