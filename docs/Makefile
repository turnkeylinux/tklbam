SOURCES = $(filter-out RelNotes%, $(wildcard *.txt))
DEPS = $(patsubst %.txt,%.man,$(SOURCES)) $(patsubst %.txt,%.html,$(SOURCES)) 

%.man: %.txt
	rst2man.py $< > $@

%.html: %.txt
	rst2html $< > $@

all: $(DEPS)

clean:
	rm -f $(DEPS)
