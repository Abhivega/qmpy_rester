import numpy as np
from collections import defaultdict
import os.path
import fractions as frac

import operator
from ..utils import *

class PhaseError(Exception):
    pass

class PhaseDataError(Exception):
    pass

class PhaseData(object):
    """
    A PhaseData object is a container for storing and organizing phase data.
    Most importantly used when doing a large number of thermodynamic analyses
    and it is undesirable to access the database for every space you want to
    consider.
    """
    def __init__(self):
        self.clear()

    def __str__(self):
        return '%d Phases' % len(self.phases)

    @property
    def phases(self):
        """
        List of all phases.
        """
        return self._phases

    @phases.setter
    def phases(self, phases):
        self.clear()
        for phase in phases:
            self.add_phase(phase)

    def clear(self):
        self._phases = []
        self.phases_by_elt = defaultdict(set)
        self.phases_by_dim = defaultdict(set)
        self.phase_dict = {}
        self.space = set()

    def add_phase(self, phase):
        """
        Add a phase to the PhaseData collection. Updates the
        PhaseData.phase_dict and PhaseData.phases_by_elt dictionaries
        appropriately to enable quick access.
        Examples::
            >>> pd = PhaseData()
            >>> pd.add_phase(Phase(composition='Fe2O3', energy=-3))
            >>> pd.add_phase(Phase(composition='Fe2O3', energy=-4))
            >>> pd.add_phase(Phase(composition='Fe2O3', energy=-5))
            >>> pd.phase_dict
            {'Fe2O3': <Phase Fe2O3 : -5}
            >>> pd.phases_by_elt['Fe']
            [<Phase Fe2O3 : -3>, <Phase Fe2O3 : -4>, <Phase Fe2O3 : -5>]
        """

        if not phase.name in self.phase_dict:
            self.phase_dict[phase.name] = phase
        else:
            if phase.energy < self.phase_dict[phase.name].energy:
                self.phase_dict[phase.name] = phase
        self._phases.append(phase)
        phase.index = len(self._phases)

        for elt in phase.comp:
            self.phases_by_elt[elt].add(phase)
        self.phases_by_dim[len(phase.comp)].add(phase)

        self.space |= set(phase.comp.keys())

    def add_phases(self, phases):
        """
        Loops over a sequence of phases, and applies `add_phase` to each.
        Equivalent to::
            >>> pd = PhaseData()
            >>> for p in phases:
            >>>     pd.add_phase(p)
        """
        for phase in phases:
            self.add_phase(phase)

    def read_api_data(self, jsondata, per_atom=True):
        if jsondata.get('data', []) == []:
            return
        for d in jsondata['data']:
            #if d.get('name', None) or d.get('delta_e', None):
            #    continue
            print(d)
            print(d.get('name'))
            phase = Phase(composition=d.get('name'),
                          energy=float(d.get('delta_e')),
                          per_atom=per_atom)
            self.add_phase(phase)

class Phase(object):
    """
    A Phase object is a point in composition-energy space.
    Examples::
        >>> p1 = Phase('Fe2O3', -1.64, per_atom=True)
        >>> p2 = Phase('Fe2O3', -8.2, per_atom=False)
        >>> p3 = Phase({'Fe':0.4, 'O':0.6}, -1.64)
        >>> p4 = Phase({'Fe':6, 'O':9}, -24.6, per_atom=False)
        >>> p1 == p2
        True
        >>> p2 == p3
        True
        >>> p3 == p4
        True
    """

    id = None
    use = True
    show_label = True
    custom_name = None
    phase_dict = {}
    def __init__(self,
            composition=None,
            energy=None,
            description='',
            per_atom=True,
            stability=None,
            total=False,
            name=''):

        if composition is None or energy is None:
            raise PhaseError("Composition and/or energy missing.")
        if isinstance(composition, str):
            composition = parse_comp(composition)

        self.description = description
        self.comp = defaultdict(float, composition)
        self.stability = stability
        if name:
            self.custom_name = name

        if not per_atom:
            self.total_energy = energy
        else:
            self.energy = energy

    @staticmethod
    def from_phases(phase_dict):
        """
        Generate a Phase object from a dictionary of Phase objects. Returns a
        composite phase of unit composition.
        """
        if len(phase_dict) == 1:
            return phase_dict.keys()[0]

        pkeys = sorted(phase_dict.keys(), key=lambda x: x.name)
        energy = sum([ amt*p.energy for p, amt in phase_dict.items() ])

        comp = defaultdict(float)
        for p, factor in phase_dict.items():
            for e, amt in p.unit_comp.items():
                comp[e] += amt*factor

        phase = Phase(
                composition=comp,
                energy=energy,
                per_atom=False)
        phase.phase_dict = phase_dict
        return phase

    @property
    def natoms(self):
        return sum(self.nom_comp.values())

    def __str__(self):
        if self.description:
            return '{name} ({description}): {energy:0.3g}'.format(
                    name=self.name, energy=self.energy, description=self.description)
        else:
            return '{name} : {energy:0.3g}'.format(
                    name=self.name, energy=self.energy)

    def __repr__(self):
        return '<Phase %s>' % self

    def __hash__(self):
        return hash((self.name, self.energy))

    def __eq__(self, other):
        """
        Phases are defined to be equal if they have the same composition and an
        energy within 1e-6 eV/atom.
        """
        if set(self.comp) != set(other.comp):
            return False
        if abs(self.energy - other.energy) > 1e-6:
           return False
        for key in self.comp:
           if abs(self.unit_comp[key]-other.unit_comp[key]) > 1e-6:
                return False
        return True

    @property
    def label(self):
        return '%s: %0.3f eV/atom' % (self.name, self.energy)

    @property
    def name(self):
        if self.custom_name:
            return self.custom_name
        if self.phase_dict:
            name_dict = dict((p, v/p.natoms) for p, v in
                    self.phase_dict.items())
            return ' + '.join('%.3g %s' % (v, p.name) for p, v in name_dict.items())
        return format_comp(self.nom_comp)

    @property
    def space(self):
        """
        Set of elements in the phase.
        """
        return set([ k for k, v in self.unit_comp.items()
            if abs(v) > 1e-6 ])

    @property
    def n(self):
        """
        Number of atoms in the total composition.
        """
        return sum(self._comp.values())

    @property
    def comp(self):
        """
        Total composition.
        """
        return self._comp

    @comp.setter
    def comp(self, composition):
        self._comp = composition
        self._unit_comp = unit_comp(composition)
        self._nom_comp = reduce_comp(composition)

    @property
    def unit_comp(self):
        """
        Unit composition.
        """
        return self._unit_comp

    @property
    def nom_comp(self):
        """
        Composition divided by the GCD. e.g. Fe4O6 becomes Fe2O3.
        """
        return self._nom_comp

    @property
    def energy(self):
        """
        Energy per atom in eV.
        """
        return self._energy

    @energy.setter
    def energy(self, energy):
        self._energy = energy
        self._total_energy = energy * sum(self.comp.values())
        self._energy_pfu = energy / sum(self.nom_comp.values())

    @property
    def total_energy(self):
        """
        Total energy for the composition as supplied (in eV).
        """
        return self._total_energy

    @total_energy.setter
    def total_energy(self, energy):
        self._total_energy = energy
        self._energy = energy/sum(self.comp.values())
        self._energy_pfu = energy / sum(self.nom_comp.values())

    @property
    def energy_pfu(self):
        """
        Energy per nominal composition. i.e. energy per Fe2O3, not Fe4O6.
        """
        return self._energy_pfu

    @energy_pfu.setter
    def energy_pfu(self, energy):
        self._energy_pfu = energy

    def amt(self, comp):
        """
        Returns a composition dictionary with the specified composition pulled
        out as 'var'.
        Examples::
            >>> phase = Phase(composition={'Fe':1, 'Li':5, 'O':8}, energy=-1)
            >>> phase.amt('Li2O')
            defaultdict(<type 'float'>, {'var': 2.5, 'Fe': 1, 'O': 5.5, 'Li': 0.0})
        """
        if isinstance(comp, Phase):
            comp = comp.comp
        elif isinstance(comp, str):
            comp = parse_comp(comp)
        residual = defaultdict(float, self.comp)
        tot = sum(residual.values())
        for c, amt in dict(comp).items():
            pres = residual[c]/amt
            for c2, amt2 in comp.items():
                residual[c2] -= pres*amt2
        residual['var'] = (tot - sum(residual.values()))
        residual['var'] /= float(sum(comp.values()))
        return residual

    def fraction(self, comp):
        """
        Returns a composition dictionary with the specified composition pulled
        out as 'var'.
        Examples::
            >>> phase = Phase(composition={'Fe':1, 'Li':5, 'O':8}, energy=-1)
            >>> phase.fraction('Li2O')
            defaultdict(<type 'float'>, {'var': 0.5357142857142858, 'Fe':
                0.07142857142857142, 'O': 0.3928571428571428, 'Li': 0.0})
        """
        if isinstance(comp, Phase):
            comp = comp.unit_comp
        elif isinstance(comp, str):
            comp = unit_comp(parse_comp(comp))
        residual = defaultdict(float, self.unit_comp)
        tot = sum(residual.values())
        for c, amt in dict(comp).items():
            pres = residual[c]/amt
            for c2, amt2 in comp.items():
                residual[c2] -= pres*amt2
        residual['var'] = (tot - sum(residual.values()))
        residual['var'] /= float(sum(comp.values()))
        return residual
