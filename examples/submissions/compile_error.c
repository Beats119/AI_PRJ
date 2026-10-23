#include <stdio.h>

/* Does not compile: the workflow must produce a partial report from
 * source-only analyzers and skip the execution-dependent metrics (D-5). */
int main(void) {
    long long a, b
    if (scanf("%lld %lld", &a, &b) != 2) {
        return 1;
    }
    printf("%lld\n", a + b);
    return 0;
}
