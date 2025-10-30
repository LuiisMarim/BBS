# Makefile para o Broker em C

CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -O2
LDFLAGS = -lzmq -lmsgpackc -lpthread
TARGET = broker
SOURCES = broker.c ../common_utils/logical_clock.c
OBJECTS = $(SOURCES:.c=.o)

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) $(OBJECTS) -o $(TARGET) $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TARGET)

run: $(TARGET)
	./$(TARGET)
