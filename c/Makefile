CC      ?= cc
CFLAGS  ?= -O2 -std=c11 -Wall -Wextra -Wpedantic
LDFLAGS ?=
LDLIBS  ?= -lm

BINARIES = crib crib_test crib_sweep

.PHONY: all test difftest bench clean

all: $(BINARIES)

crib: cli.o cribbage.o opponent_model_data.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

crib_test: test_cribbage.o cribbage.o opponent_model_data.o
	$(CC) $(CFLAGS) -o $@ $^ $(LDFLAGS) $(LDLIBS)

crib_sweep: sweep.o cribbage.o opponent_model_data.o
	$(CC) $(CFLAGS) -pthread -o $@ $^ $(LDFLAGS) $(LDLIBS)

%.o: %.c cribbage.h
	$(CC) $(CFLAGS) -c -o $@ $<

test: crib_test			## run the C correctness suite
	./crib_test

difftest: crib			## check the C against cribbage.py
	python3 tools/difftest.py

clean:
	rm -f $(BINARIES) *.o
