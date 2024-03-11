# RUN THIS CODE ON PYTHON 3.8.18 FOR BEST RESULTS
# INSTALL REQUIRED DEPENDENCIES USING '$ pip install -r requirements.txt'

import click
from datetime import datetime
from typing import List, Dict
from midiutil import MIDIFile
from pyo import *
from algorithms.genetic import generate_genome, Genome, selection_pair, single_point_crossover, mutation

BITS_PER_NOTE = 4
KEYS = ["C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"]
SCALES = ["major", "minorM", "dorian", "phrygian", "lydian", "mixolydian", "majorBlues", "minorBlues"]

# calculates integer value from 0 and 1s
def int_from_bits(bits: List[int]) -> int:
    return int(sum([bit*pow(2, index) for index, bit in enumerate(bits)]))

# uses genome and translate it into notes. iterate over each note, no. of bar multipliy no. of notes is total number of notes
# iterates over each note, take the every 4 bits and put them into a list, to get a list of lists
def genome_to_melody(genome: Genome, num_bars: int, num_notes: int, num_steps: int,
                     pauses: int, key: str, scale: str, root: int) -> Dict[str, list]:
    notes = [genome[i * BITS_PER_NOTE:i * BITS_PER_NOTE + BITS_PER_NOTE] for i in range(num_bars * num_notes)]

    # default length for 1 note in PYO is 4 ticks, 4 quarter notes is 1 bar, for 4 notes in bar = note length of 1, 2 notes in bar = length 2, 8 notes in bar = length 0.5
    note_length = 4 / float(num_notes)
    scl = EventScale(root=key, scale=scale, first=root)

    # generates melody object, have notes, velocity and beat
    melody = {
        "notes": [],
        "velocity": [],
        "beat": []
    }

    # accesses list in lists, go through each 4 bits in a note, generate an integer from them
    for note in notes:
        integer = int_from_bits(note)

        # 3 bits are use for the pitch of the note, 1 bit i s used for if its a pause or not
        # if no pauses, remap all notes inside the 3 bit range, use modulo operator, 2 to power of bits -1, move over to 3 bits, therefore no pauses
        if not pauses:
            integer = int(integer % pow(2, BITS_PER_NOTE - 1))

        # if number higherr than 2 to power of bits per note -1, write note with veolicty 0 into melody, which has no sound equal to a pause
        if integer >= pow(2, BITS_PER_NOTE - 1):
            melody["notes"] += [0]
            melody["velocity"] += [0]
            melody["beat"] += [note_length]
        else:
            # increases the length of last note to prevent any awkward rest in music
            if len(melody["notes"]) > 0 and melody["notes"][-1] == integer:
                melody["beat"][-1] += note_length
            else:
                melody["notes"] += [integer]
                melody["velocity"] += [127]
                melody["beat"] += [note_length]

    # multiple steps, add number of steps to generate the chords over each note. replace all normal melody as steps
    steps = []
    for step in range(num_steps):
        steps.append([scl[(note+step*2) % len(scl)] for note in melody["notes"]])
    melody["notes"] = steps
    return melody

    # translates the melody object generated in to events to make it readable for the pyo server
def genome_to_events(genome: Genome, num_bars: int, num_notes: int, num_steps: int,
                     pauses: bool, key: str, scale: str, root: int, bpm: int) -> [Events]:
    melody = genome_to_melody(genome, num_bars, num_notes, num_steps, pauses, key, scale, root)

    return [
        Events(
            midinote=EventSeq(step, occurrences=1),
            midivel=EventSeq(melody["velocity"], occurrences=1),
            beat=EventSeq(melody["beat"], occurrences=1),
            attack=0.001,
            decay=0.05,
            sustain=0.5,
            release=0.005,
            bpm=bpm
        ) for step in melody["notes"]
    ]

# fitness function gets the genome, the pyo server, parameters used to translate the genome into events used to play via the pyo server 
def fitness(genome: Genome, s: Server, num_bars: int, num_notes: int, num_steps: int,
            pauses: bool, key: str, scale: str, root: int, bpm: int) -> int:
    m = metronome(bpm)

    events = genome_to_events(genome, num_bars, num_notes, num_steps, pauses, key, scale, root, bpm)
    for e in events:
        e.play()
    s.start()

    # fitness value to be used to generate next generation of melodies
    rating = input("Rating (0-5)")

    # played for each voice in number of steps 
    for e in events:
        e.stop()
    s.stop()
    time.sleep(1)
    try:
        rating = int(rating)
    except ValueError:
        rating = 0
    return rating

# copies from PYO documentation, doing ticking sound for reference of melody bpm 
def metronome(bpm: int):
    met = Metro(time=1 / (bpm / 60.0)).play()
    t = CosTable([(0, 0), (50, 1), (200, .3), (500, 0)])
    amp = TrigEnv(met, table=t, dur=.25, mul=1)
    freq = Iter(met, choice=[660, 440, 440, 440])
    return Sine(freq=freq, mul=amp).mix(2).out()

# saves genome to midi, generate midi file with a track and channel with added time and bpm
def save_genome_to_midi(filename: str, genome: Genome, num_bars: int, num_notes: int, num_steps: int,
                        pauses: bool, key: str, scale: str, root: int, bpm: int):
    melody = genome_to_melody(genome, num_bars, num_notes, num_steps, pauses, key, scale, root)
    if len(melody["notes"][0]) != len(melody["beat"]) or len(melody["notes"][0]) != len(melody["velocity"]):
        raise ValueError
    mf = MIDIFile(1)
    track = 0
    channel = 0
    time = 0.0
    mf.addTrackName(track, time, "Sample Track")
    mf.addTempo(track, time, bpm)

    # if velocity more than 0, add notes for each melody step and increase time
    for i, vel in enumerate(melody["velocity"]):
        if vel > 0:
            for step in melody["notes"]:
                mf.addNote(track, channel, step[i], time, melody["beat"][i], vel)
        time += melody["beat"][i]

    # creates folder and saves
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "wb") as f:
        mf.writeFile(f)

# main functions, click library, define a number of parameters the program can query when it starts
@click.command()
@click.option("--num-bars", default=8, prompt='Number of bars (length of the generated melody):', type=int)
@click.option("--num-notes", default=8, prompt='Notes per bar:', type=int)
@click.option("--num-steps", default=1, prompt='Number of steps (having 2 or more leads to chords being produced):', type=int)
@click.option("--pauses", default=True, prompt='Introduce Pauses?', type=bool)
@click.option("--key", default="C", prompt='Key:', type=click.Choice(KEYS, case_sensitive=False))
@click.option("--scale", default="major", prompt='Scale:', type=click.Choice(SCALES, case_sensitive=False))
@click.option("--root", default=4, prompt='Scale Root (higher values leads to higher pitch):', type=int)
@click.option("--population-size", default=4, prompt='Population size (number of melodies per generation to rate and recombine):', type=int)
@click.option("--num-mutations", default=2, prompt='Number of mutations (Max number of mutations per melody):', type=int)
@click.option("--mutation-probability", default=0.5, prompt='Mutations probability:', type=float)
@click.option("--bpm", default=170, prompt='Beats per minute:', type=int)
def main(num_bars: int, num_notes: int, num_steps: int, pauses: bool, key: str, scale: str, root: int,
         population_size: int, num_mutations: int, mutation_probability: float, bpm: int):

    # folder is saved with date and timestamp to keep folders unique
    folder = str(int(datetime.now().timestamp()))

    # generates a random set of genomes and save as population, 2 bars, 8 notes, 16 notes in 1 genome.number of bits for 1 note is 4.every 4 bits is one note, every 4 bits x 8 per bar is the whole melody
    population = [generate_genome(num_bars * num_notes * BITS_PER_NOTE) for _ in range(population_size)]

    # starts the PYO server to play the melodies
    s = Server().boot()

    population_id = 0

    # program runs on startup and Y command on Continue. running set to false and program ends on N command on continue
    running = True
    while running:
        # takes all genomes and place them in random order
        random.shuffle(population)

        # evalutes fitness function where we score through our ratings in the program
        population_fitness = [(genome, fitness(genome, s, num_bars, num_notes, num_steps, pauses, key, scale, root, bpm)) for genome in population]

        # sorts from best rated to worst rated
        sorted_population_fitness = sorted(population_fitness, key=lambda e: e[1], reverse=True)

        # generates new population by using genome from sorted population fitness
        population = [e[0] for e in sorted_population_fitness]

        # takes first two elements of each population and put it in the next generation as elitism applied
        next_generation = population[0:2]

        # takes the first 2 genomes from the population, do single point crossover,assign a random point in the genome, take first half of first parent
        # and second half of second parent, and vice versa, producing offspring a and b
        for j in range(int(len(population) / 2) - 1):
            
            # fitness_lookup function gets fitness or each entry of population and uses weight, thehigher the fitness is, the more weight it is, more liklely to be chosen for next generation 
            # looks up oppulation_fitness list, searching for genome entry looked for, and return fitness value
            def fitness_lookup(genome):
                for e in population_fitness:
                    if e[0] == genome:
                        return e[1]
                return 0
            parents = selection_pair(population, fitness_lookup)
            offspring_a, offspring_b = single_point_crossover(parents[0], parents[1])
            offspring_a = mutation(offspring_a, num=num_mutations, probability=mutation_probability)
            offspring_b = mutation(offspring_b, num=num_mutations, probability=mutation_probability)
            next_generation += [offspring_a, offspring_b]
            # next generation, new  2 genomes from elitism and 2 offsrping from single point crossover
            # uses mutation function to mutate offspring a and b and put them in new generation

        print(f"population {population_id} done")

        # translates genome into events sent to PYO server to generate melody, plays the best rated music
        events = genome_to_events(population[0], num_bars, num_notes, num_steps, pauses, key, scale, root, bpm)
        for e in events:
            e.play()
        s.start()
        input("here is the no1 hit …")
        s.stop()
        for e in events:
            e.stop()
        time.sleep(1)

        # plays the second best generated music
        events = genome_to_events(population[1], num_bars, num_notes, num_steps, pauses, key, scale, root, bpm)
        for e in events:
            e.play()
        s.start()
        input("here is the second best …")
        s.stop()
        for e in events:
            e.stop()
        time.sleep(1)

        # saves genome to midi, put in folder names uniquely, with scale and key 
        print("saving population midi …")
        for i, genome in enumerate(population):
            save_genome_to_midi(f"{folder}/{population_id}/{scale}-{key}-{i}.mid", genome, num_bars, num_notes, num_steps, pauses, key, scale, root, bpm)
        print("done")
        running = input("continue? [Y/n]") != "n"
        population = next_generation
        population_id += 1


if __name__ == '__main__':
    main()
