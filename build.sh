#!/bin/sh
set -eu
cd "$(dirname "$0")"
mkdir -p build private
chmod 700 private
xcrun clang -Wall -Wextra -Werror inspect.c -framework IOKit -framework CoreFoundation -o build/keychron-battery
xcrun clang -Wall -Wextra -Werror battery.c -framework IOKit -framework CoreFoundation -o build/keychron-raw-battery
xcrun clang -Wall -Wextra -Werror test_inspect.c -framework IOKit -framework CoreFoundation -o build/test-inspect
./build/test-inspect
