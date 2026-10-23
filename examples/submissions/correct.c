#include <stdio.h>

/* Adds two integers using a wider type, so large sums are correct. */
static long long add(long long lhs, long long rhs) {
    return lhs + rhs;
}

int main(void) {
    long long lhs, rhs;
    if (scanf("%lld %lld", &lhs, &rhs) != 2) {
        return 1;
    }
    printf("%lld\n", add(lhs, rhs));
    return 0;
}
