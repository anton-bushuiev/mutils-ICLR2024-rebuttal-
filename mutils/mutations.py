import itertools
import copy
import warnings
import math

import Bio.PDB

from mutils.proteins import AMINO_ACID_CODES_1
from mutils.pdb import load_pdb
from mutils.misc import verbose


class Mutation:
    def __init__(self, mutstr='', muttuple=()):
        """
        :param mut: String-represented single or multi-point mutation.
            Example of the string for a double point mutation: YC17T,TA20A.
            Here, point mutations are separated with comma and in the form
            <Wild-type residue><Chain id><Residue number><Mutated residue>
        """
        # TODO Check format

        # Check datatypes
        if not isinstance(muttuple, tuple):
            try:
                muttuple = tuple(muttuple)
            except:
                raise ValueError('Wrong `muttuple` datatype')

        # Init both representations
        if mutstr != '' and muttuple != ():
            raise ValueError('Wrong constructor argument values.')
        elif mutstr != '':
            self.muttuple = tuple(mutstr.replace(' ', '').split(','))
        else:
            self.muttuple = muttuple

    def revert(self):
        """
        Example: YC17T -> TC17Y
        :return: Reversed mutation
        """
        return Mutation(muttuple=tuple(map(self.revert_single, self.muttuple)))

    @verbose
    def is_mutation_reversed(self, pdbfile, model_id=0):
        """
        Check if mutation is reversed or direct with respect to the PDB file.
        :param pdbfile: PDB file corresponding to current Mutation instance
        :param model_id: Model id in PDB file
        :return: Bool
        """
        # Select first mutation
        # (Relaxed to check only the first one for better performance)
        mut = self.muttuple[0]

        # Parse mutation info
        wtres, chainid, pos, mutres = mut[0], mut[1], int(mut[2:-1]), mut[-1]

        # Read structure
        warnings.simplefilter('ignore')
        model = Bio.PDB.PDBParser().get_structure(None, pdbfile)[model_id]

        # Check mutated amino acid
        resname = model[chainid][pos].get_resname()
        resname = Bio.PDB.Polypeptide.three_to_one(resname)
        if resname == wtres:
            return False
        elif resname == mutres:
            return True
        else:
            raise ValueError(f'{mut} is neither forward nor reverse.')

    def rename_chains(self, dct):
        """
        :param dct: Rename dict. For example {'C': 'A'} to replace chaind 'C'
            for 'A'
        :return: Mutation with renamed chains
        """
        return Mutation(muttuple=tuple(map(
            lambda mut: self.rename_chains_single(mut, dct), self.muttuple
        )))

    @staticmethod
    def parse_single(mut):
        if len(mut) == 0:
            return None, None, None, None
        # TODO Not general enough
        # Chain may be missing, chain may be more than 1 character
        else:
            return mut[0], mut[1], int(mut[2:-1]), mut[-1]

    @staticmethod
    def revert_single(mut):
        return mut[-1] + mut[1:-1] + mut[0]

    @staticmethod
    def rename_chains_single(mut, dct):
        return mut[:1] + dct[mut[1]] + mut[2:]

    def __str__(self):
        return ','.join(self.muttuple)

    def __repr__(self):
        return f'Mutation({str(self)})'


class MutationSpace:
    def __init__(self, dct=None, lst=None):
        """
        :param dct:
            Example: {
                'YC17': 'AG',
                'TA20': 'A',
                '5C': ''
            }
        """
        if dct is not None and lst is not None:
            raise ValueError('Both `dct` and `lst` passed.')

        self.dct = dct
        if lst is None and self.dct is not None:
            self.lst = self._dict_to_list(self.dct)
        else:
            self.lst = lst
        self.n_pos = len(self.lst)

    def size(self, d: int = None, wt: bool = False) -> int:
        """
        Calculate the size of the d-order subspace.
        :param d: Degree of mutations. I.e. d-point mutations are counted.
            All are counted if not specified
        :param wt: True to count wild type (identity mutation).
        :return: Total number of mutations in specified subspace
        """
        if d is None:
            # TODO just prod(len(val)+1)-1  for all dct values
            return sum([self.size(d) for d in range(1, self.n_pos + 1)])

        retval = 1 if wt else 0

        if d == 0:
            return retval

        combs = itertools.combinations(range(len(self.lst)), d)
        for comb in combs:
            retval += math.prod([len(self.lst[i]) for i in comb])

        return retval

    def construct(self, d: int = None, n: int = None) -> list:
        """
        Generate multi-point mutations from space
        :param d: Degree of mutations. I.e. d-point mutations are generated.
        :param n: Maximum number of mutations. All generated if not specified.
        :return:
        """
        # TODO implement for n
        if n is not None:
            raise NotImplementedError()

        # Return empty space is d equals 0
        if d == 0:
            return []

        # Generate d-point space by generating full spaces for all
        # d-combinations
        if d is not None and d != -1:
            combs = itertools.combinations(self.lst, d)
            retval = []
            for comb in combs:
                retval += MutationSpace(lst=comb).construct(d=-1)
            return retval

        # Generate full space
        retval = self.lst
        # add "leave wild type" mutation at each position
        if d != -1:
            retval = map(lambda x: x + [''], retval)
        # product
        retval = itertools.product(*retval)
        # remove "leave wild type" mutations from combinations
        retval = map(lambda m: list(filter(lambda s: s != '', m)), retval)
        # convert to single string format
        retval = list(map(lambda x: ','.join(x), retval))
        # remove identity mutations
        if d != -1:
            retval.remove('')
        return retval

    @classmethod
    def from_affilib(cls, affilib_path, pdb_path):
        # Read PDB
        model = load_pdb(pdb_path, model_id=0, verbose=False)

        # Read Affilib output file
        with open(affilib_path, 'r') as file:
            rows = file.readlines()

        # Parse Affilib output file
        dct_raw = dict(list(map(lambda row: row.split(), rows)))
        dct = {}
        for key_raw, value_raw in dct_raw.items():
            # Remove wild type
            pos, chainid = int(key_raw[:-1]), key_raw[-1]
            wt = Bio.PDB.Polypeptide.three_to_one(model[chainid][pos].
                                                  get_resname())
            value = value_raw.replace(wt, '')
            if len(value) == len(value_raw):
                raise ValueError(f'Residue list does not contain'
                                 f' wild type {wt} on {key_raw}')
            # Reformat key
            key = f'{wt}{chainid}{pos}'

            dct[key] = value

        # Init MutationSpace
        return cls(dct=dct)

    # def write(self, outdir, chunk_size):
    #     mutations = self.construct()
    #     save_list_in_chunks(
    #       mutations, chunk_size=chunk_size, out_dir_path=outdir
    #     )

    @staticmethod
    def _dict_to_list(dct):
        """
        :param dct: Example:
            {
                'YC17': 'AG',
                'TA20': 'A',
                '5C': ''
            }
        :return:
            [
                ['YC17A', 'YC17G'],
                ['TA20A'],
                []
            ]
        """
        return [
            [pref + mt for mt in mts]
            for pref, mts in dct.items()
        ]

    def __repr__(self):
        return f'MutationSpace({self.dct})'


@verbose
def is_residue_wt(pdbfile, chainid, pos, res, model_id=0):
    """
    Check if residue `res` at position `pos` in chain `chain` is indeed
    in PDB structure.
    :param pdbfile: PDB file corresponding to current Mutation instance.
    :param pos: Position of tested residue
    :param pos: Residue one capital letter code
    :param model_id: Model id in PDB file
    :return: Bool
    """
    # Read structure
    warnings.simplefilter('ignore')
    model = load_pdb(pdbfile, model_id=model_id)

    # Check mutated amino acid
    res_true = model[chainid][pos].get_resname()
    res_true = Bio.PDB.Polypeptide.three_to_one(res_true)
    return res == res_true
