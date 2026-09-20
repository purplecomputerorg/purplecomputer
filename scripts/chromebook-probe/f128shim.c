/* ChromeOS's glibc is built without the _Float128 API. onnxruntime's bundled libstdc++
   references strfromf128 (std::to_chars) but never formats a float128 in practice. */
#include <stdio.h>
int strfromf128(char *s, size_t n, const char *fmt, __float128 f) { return snprintf(s, n, fmt, (double)f); }
