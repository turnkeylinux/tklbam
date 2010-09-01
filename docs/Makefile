DEPS = $(patsubst %.txt,%.man,$(wildcard *.txt))

%.man: %.txt
	rst2man.py $< > $@

all: $(DEPS)

clean:
	rm -f $(DEPS)
