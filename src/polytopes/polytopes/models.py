"""
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Classes for building models of 3D/4D/5D uniform polytopes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

See the doc: "https://neozhaoliang.github.io/polytopes/"

"""
from itertools import combinations
import numpy as np

from . import helpers
from .coxeter_plane import draw_on_coxeter_plane
from .povray import export_polytope_data
from .todd_coxeter import CosetTable


class BasePolytope(object):

    """
    Base class for building uniform polytopes using Wythoff's construction.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        """
        :param coxeter_diagram: a tuple of rational numbers.
            Coxeter diagram for this polytope.

        :param init_dist: a tuple of non-negative floats.
            distances between the initial vertex and the mirrors.

        :param extra_relations: a tuple of tuples of integers.
            a presentation of a star polytope can be obtained by imposing more
            relations on the generators. For example "(ρ₀ρ₁ρ₂ρ₁)^n = 1" for some
            integer n, where n is the number of sides of a hole.
            See Coxeter's article

                "Regular skew polyhedra in three and four dimensions,
                 and their topological analogues"

        """
        # Coxeter matrix of the symmetry group
        self.coxeter_matrix = helpers.get_coxeter_matrix(coxeter_diagram)

        # reflection mirrors stored as row vectors in a matrix
        self.mirrors = helpers.get_mirrors(coxeter_diagram)

        # reflection transformations about the mirrors
        self.reflections = tuple(helpers.reflection_matrix(v) for v in self.mirrors)

        # the initial vertex
        self.init_v = helpers.get_init_point(self.mirrors, init_dist)

        # a mirror is active if and only if the initial vertex has non-zero distance to it
        self.active = tuple(bool(x) for x in init_dist)

        # generators of the symmetry group
        self.symmetry_gens = tuple(range(len(self.coxeter_matrix)))

        # relations between the generators
        self.symmetry_rels = tuple(
            (i, j) * self.coxeter_matrix[i][j]
            for i, j in combinations(self.symmetry_gens, 2)
        )
        # add the extra relations between generators (only used for star polytopes)
        self.symmetry_rels += tuple(extra_relations)

        # multiplication table bwteween the vertices
        self.vtable = None
        # word representations of the vertices
        self.vwords = None

        # number of vertices, edges, faces
        self.num_vertices = 0
        self.num_edges = 0
        self.num_faces = 0

        # coordinates of the vertices, indices of the edges and faces
        self.vertices_coords = []
        self.edge_indices = []
        self.face_indices = []

    def build_geometry(self):
        """Put the building procedure into three functions.
        """
        self.get_vertices()
        self.get_edges()
        self.get_faces()

    def get_vertices(self):
        """
        This method computes the following data that will be used later:

        1. a coset table for the vertices.
        2. a complete list of word representations of the vertices.
        3. coordinates of the vertices.
        """
        # generators of the stabilizing subgroup that fixes the initial vertex.
        vgens = [(i,) for i, active in enumerate(self.active) if not active]
        self.vtable = CosetTable(self.symmetry_gens, self.symmetry_rels, vgens)
        self.vtable.run()
        # word representations of the vertices
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        # apply words of the vertices to the initial vertex to get all vertices
        self.vertices_coords = np.array([
            self.transform(self.init_v, w) for w in self.vwords
        ])

    def get_edges(self):
        """
        Compute the indices of all edges.
        
        1. If the initial vertex v₀ lies on the mirror mᵢ then the reflection
        ρᵢ fixes v₀, hence there are no edges of type i.
        
        2. Otherwise, v₀ and its virtual image v₁ about mᵢ generate a base edge
        e₀, the stabilizing subgroup of e₀ is generated by ρᵢ together those
        simple reflections ρⱼ such that ρⱼ fixes v₀ and commutes with ρᵢ: ρᵢρⱼ=ρⱼρᵢ.
        Again we use Todd-Coxeter's procedure to get a complete list of word
        representations for the edges of type i and apply them to e₀ to get all
        edges of type i.
        """
        for i, active in enumerate(self.active):
            # if there are edges of type i
            if active:
                # the initial edge
                e0 = (0, self.move(0, (i,)))
                # generators of the edge stabilizing subgroup
                egens = [(i,)] + self.get_orthogonal_stabilizing_mirrors((i,))
                # get word representations of the edges
                coset_reps = self.get_coset_representatives(egens)
                # apply them to the base edge to get all edges of type i
                orbit = self.get_orbit(coset_reps, e0)
                self.edge_indices.append(orbit)
                self.num_edges += len(orbit)

    def get_faces(self):
        """
        Compute the indices of all faces.
        The composition of two reflections ρᵢ and ρⱼ is a rotation that
        fixes a base face f₀. The stabilizing subgroup of f₀ is generated
        by {ρᵢ, ρⱼ} together with those simple reflections ρₖ such that ρₖ
        fixes v₀ and commutes with both ρᵢ and ρⱼ.
        """
        for i, j in combinations(self.symmetry_gens, 2):
            m = self.coxeter_matrix[i][j]
            f0 = []
            # if both two mirrors are active then they generate a face
            if self.active[i] and self.active[j]:
                for k in range(m):
                    f0.append(self.move(0, (i, j) * k))
                    f0.append(self.move(0, (j,) + (i, j) * k))
            # if exactly one of the two mirrors are active then they
            # generate a face only when they are not perpendicular
            elif (self.active[i] or self.active[j]) and m > 2:
                for k in range(m):
                    f0.append(self.move(0, (i, j) * k))
            # else they do not generate a face
            else:
                continue

            # generators of the face stabilizing subgroup
            fgens = [(i,), (j,)] + self.get_orthogonal_stabilizing_mirrors([i, j])
            coset_reps = self.get_coset_representatives(fgens)
            # apply the coset representatives to the base face
            orbit = self.get_orbit(coset_reps, f0)
            self.face_indices.append(orbit)
            self.num_faces += len(orbit)

    def transform(self, vector, word):
        """
        Transform a vector by a word in the symmetry group.
        Return the coordinates of the resulting vector.
 
        :param vector: a 1d array, e.g. (1, 0, 0).
        :param word: a list of integers.
        """
        for w in word:
            vector = np.dot(vector, self.reflections[w])
        return vector

    def move(self, vertex, word):
        """
        Transform a vertex by a word in the symmetry group.
        Return the index of the resulting vertex.
        
        :param vertex: an integer.
        :param word: a list of integers.
        """
        for w in word:
            vertex = self.vtable[vertex][w]
        return vertex

    def get_orthogonal_stabilizing_mirrors(self, subgens):
        """
        Given a list of generators in `subgens`, return the generators that
        commute with all of those in `subgens` and fix the initial vertex.
  
        :param subgens: a list of generators, e.g. [0, 1]
        """
        result = []
        for s in self.symmetry_gens:
            # check commutativity
            if all(self.coxeter_matrix[x][s] == 2 for x in subgens):
                # check if it fixes v0
                if not self.active[s]:
                    result.append((s,))
        return result

    def get_coset_representatives(self, subgens, coxeter=True):
        """
        Get the set of coset representatives of a subgroup generated
        by `subgens`.

        :param subgens:
            a list of generating words of the subgroup, e.g. [(0,), (1, 2)]
        """
        table = CosetTable(self.symmetry_gens, self.symmetry_rels, subgens, coxeter)
        table.run()
        return table.get_words()

    def get_orbit(self, coset_reps, base):
        """
        Apply the words in `coset_reps` to a base edge/face.
 
        :param coset_reps: a list of words.
        :param base: a 1d list of integers.
        """
        return [[self.move(v, word) for v in base] for word in coset_reps]

    def get_latex_format(self, symbol=r"\rho", cols=3, snub=False):
        """
        Return the words of the vertices in latex format.
        `cols` is the number of columns of the output latex array.
        """

        def to_latex(word):
            if not word:
                return "e"
            if snub:
                return "".join(symbol + "_{{{}}}".format(i // 2) for i in word)
            return "".join(symbol + "_{{{}}}".format(i) for i in word)

        latex = ""
        for i, word in enumerate(self.vwords):
            if i > 0 and i % cols == 0:
                latex += r"\\"
            latex += to_latex(word)
            if i % cols != cols - 1:
                latex += "&"

        return r"\begin{{array}}{{{}}}{}\end{{array}}".format("l" * cols, latex)

    def get_povray_data(self):
        return export_polytope_data(self)

    def draw_on_coxeter_plane(self, *args, **kwargs):
        draw_on_coxeter_plane(self, *args, **kwargs)


class Polyhedra(BasePolytope):

    """Base class for 3d polyhedron.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if not len(coxeter_diagram) == len(init_dist) == 3:
            raise ValueError("Length error: the inputs must all have length 3")
        super().__init__(coxeter_diagram, init_dist, extra_relations)


class Snub(Polyhedra):

    """
    A snub polyhedra is generated by the subgroup that consists of only
    rotations in the full symmetry group. This subgroup has presentation

        <r, s | r^p = s^q = (rs)^2 = 1>

    where r = ρ₀ρ₁, s = ρ₁ρ₂ are two rotations.
    Again we solve all words in this subgroup and then use them to
    transform the initial vertex to get all vertices.
    """

    def __init__(
            self,
            coxeter_diagram,
            init_dist=(1.0, 1.0, 1.0),
            extra_relations=()
        ):
        super().__init__(coxeter_diagram, init_dist, extra_relations)
        # the representation is not in the form of a Coxeter group,
        # we must overwrite the relations.

        # four generators (r, r^-1, s, s^-1)
        self.symmetry_gens = (0, 1, 2, 3)

        # relations in order:
        # 1. r^p = 1
        # 2. s^q = 1
        # 3. (rs)^2 = 1
        # 4. rr^-1 = 1
        # 5. ss^-1 = 1
        self.symmetry_rels = (
            (0,) * self.coxeter_matrix[0][1],
            (2,) * self.coxeter_matrix[1][2],
            (0, 2) * self.coxeter_matrix[0][2],
            (0, 1),
            (2, 3),
        )
        # map the extra_relations expressed by reflections
        # into relations by (r, s).
        for extra_rel in extra_relations:
            if len(extra_rel) % 2 == 1:
                extra_rel += extra_rel

            snub_rel = []
            for x, y in zip(extra_rel[:-1:2], extra_rel[1::2]):
                snub_rel.extend(
                    {
                        (0, 1): [0],
                        (0, 2): [0, 2],
                        (1, 0): [1],
                        (1, 2): [2],
                        (2, 0): [2, 0],
                        (2, 1): [3],
                    }[(x, y)]
                )
            self.symmetry_rels += (tuple(snub_rel),)

        # order of the generator rotations {rotation: order}
        # {r: p, s: q, rs: 2}
        self.rotations = {
            (0,): self.coxeter_matrix[0][1],
            (2,): self.coxeter_matrix[1][2],
            (0, 2): self.coxeter_matrix[0][2],
        }

    def get_vertices(self):
        """Get the vertices of this snub polyhedra.
        """
        # the stabilizing subgroup of the initial vertex contains only 1
        self.vtable = CosetTable(
            self.symmetry_gens, self.symmetry_rels, coxeter=False
        )
        self.vtable.run()
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        self.vertices_coords = tuple(
            self.transform(self.init_v, w) for w in self.vwords
        )

    def get_edges(self):
        """
        Get the edge indices of this snub polyhedra.
        Each rotation of the three "fundamental rotations" {r, s, rs}
        generates a base edge e, the stabilizing subgroup of e is <1>
        except that this rotation has order 2, i.e. a rotation generated
        by two commuting reflections. In this case the stabilizing subgroup
        is the cyclic group <rot> of order 2.
        """
        for rot in self.rotations:
            # if this rotation has order 2, then the edge stabilizing subgroup
            # is the cyclic subgroup <rot>
            if self.rotations[rot] == 2:
                egens = (rot,)
                coset_reps = self.get_coset_representatives(egens, coxeter=False)
            # else the edge stabilizing subgroup is <1>
            else:
                coset_reps = self.vwords

            e0 = (0, self.move(0, rot))  # the base edge
            # apply coset representatives to e0 to get all edges
            orbit = self.get_orbit(coset_reps, e0)
            self.edge_indices.append(orbit)
            self.num_edges += len(orbit)

    def get_faces(self):
        """
        Get the face indices of this snub polyhedra.
        Each rotation of the three "fundamental rotations" {r, s, rs}
        generates a base face f₀ if the order of this rotation is strictly
        greater than two, else it only gives an edge (degenerated face).

        There's another type of face given by the relation r*s = rs:
        it's generated by the three vertices {v₀, v₀s, v₀rs}.
        Note (v₀, v₀s) is an edge of type s, (v₀, v₀rs) is an edge of type rs,
        (v₀s, v₀rs) is an edge of type r since it's in the same orbit of the
        edge (v₀, v₀r) by applying s on it.
        """
        for rot, order in self.rotations.items():
            # if the order of this rotation is > 2 then it generates a face
            if order > 2:
                f0 = tuple(self.move(0, rot * k) for k in range(order))
                # the stabilizing group is the cyclic group <rot>
                fgens = (rot,)
                coset_reps = self.get_coset_representatives(fgens, coxeter=False)
                orbit = self.get_orbit(coset_reps, f0)
                self.face_indices.append(orbit)
                self.num_faces += len(orbit)

        # handle the special triangle face (v0, v0s, v0rs)
        # note its three edges are in different orbits so
        # its stabilizing subgroup must be <1>.
        triangle = (0, self.move(0, (2,)), self.move(0, (0, 2)))
        orbit = self.get_orbit(self.vwords, triangle)
        self.face_indices.append(orbit)
        self.num_faces += len(orbit)

    def transform(self, vector, word):
        """
        Transform a vector by a word in the group.
        Return the coordinates of the resulting vector.
        Note generator 0 means r = ρ₀ρ₁, generator 1 means s = ρ₁ρ₂.
        """
        for g in word:
            if g == 0:
                vector = np.dot(vector, self.reflections[0])
                vector = np.dot(vector, self.reflections[1])
            else:
                vector = np.dot(vector, self.reflections[1])
                vector = np.dot(vector, self.reflections[2])
        return vector


class Polychora(BasePolytope):

    """Base class for 4d polychoron.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if not (len(coxeter_diagram) == 6 and len(init_dist) == 4):
            raise ValueError(
                "Length error: the input coxeter_diagram must have length 6 and init_dist has length 4"
            )
        super().__init__(coxeter_diagram, init_dist, extra_relations)


class Polytope5D(BasePolytope):

    """Base class for 5d uniform polytopes.
    """

    def __init__(self, coxeter_diagram, init_dist, extra_relations=()):
        if len(coxeter_diagram) != 10 and len(init_dist) != 5:
            raise ValueError(
                "Length error: the input coxeter_diagram must have length 10 and init_dist has length 5"
            )
        super().__init__(coxeter_diagram, init_dist, extra_relations)

    def proj4d(self, pole=1.3):
        """Stereographic project vertices to 4d.
        """
        self.vertices_coords = [v[:4] / (pole - v[-1]) for v in self.vertices_coords]
        return self


class Snub24Cell(Polychora):

    """
    The snub 24-cell can be constructed from snub demitesseract [3^(1,1,1)]+,
    the procedure is similar with snub polyhedron above.
    Coxeter-Dynkin diagram:

        ρ₀    ρ₁    ρ₂
        •-----•-----•
              |
              •
              ρ₃

    Its symmetric group is generated by three rotations {r, s, t}, where r = ρ₀ρ₁,
    s = ρ₁ρ₂, t = ρ₁ρ₃. A presentation is

           G = <r, s, t | r^3 = s^3 = t^3 = (rs)^2 = (rt)^2 = (s^-1 t)^2 = 1>

    """

    def __init__(self):
        coxeter_diagram = (3, 2, 2, 3, 3, 2)
        active = (1, 1, 1, 1)
        super().__init__(coxeter_diagram, active, extra_relations=())
        # generators in order: {r, r^-1, s, s^-1, t, t^-1}
        self.symmetry_gens = tuple(range(6))
        # relations in order:
        # 1. r^3 = 1
        # 2. s^3 = 1
        # 3. t^3 = 1
        # 4. (rs)^2 = 1
        # 5. (rt)^2 = 1
        # 6. (s^-1t)^2 = 1
        # 7. rr^-1 = 1
        # 8. ss^-1 = 1
        # 9. tt^-1 = 1
        self.symmetry_rels = (
            (0,) * 3,
            (2,) * 3,
            (4,) * 3,
            (0, 2) * 2,
            (0, 4) * 2,
            (3, 4) * 2,
            (0, 1),
            (2, 3),
            (4, 5),
        )
        # rotations and their order
        # {r: 3, s: 3, t: 3, rs: 2, rt: 2, s^-1t: 2}
        self.rotations = {(0,): 3, (2,): 3, (4,): 3, (0, 2): 2, (0, 4): 2, (3, 4): 2}

    def get_vertices(self):
        """Get the coordinates of the snub 24-cell.
        """
        self.vtable = CosetTable(
            self.symmetry_gens, self.symmetry_rels, coxeter=False
        )
        self.vtable.run()
        self.vwords = self.vtable.get_words()
        self.num_vertices = len(self.vwords)
        self.vertices_coords = tuple(
            self.transform(self.init_v, w) for w in self.vwords
        )

    def get_edges(self):
        """Get the edges of the snub 24-cell. Again each fundamental rotation
        in {r, s, t, rs, rt, s^-1t} generates edges of its type.
        """
        for rot, order in self.rotations.items():
            # the initial edge
            e0 = (0, self.move(0, rot))
            # if the rotation has order 2 then the stabilizing subgroup of
            # the init edge is the cyclic subgroup <rot>, else it's <1>.
            if order == 2:
                egens = (rot,)
                coset_reps = self.get_coset_representatives(egens, coxeter=False)
            else:
                coset_reps = self.vwords

            orbit = self.get_orbit(coset_reps, e0)
            self.edge_indices.append(orbit)
            self.num_edges += len(orbit)

    def get_faces(self):
        """
        Get the faces of the snub 24-cell.

        1. A fundamental rotation generates a face by rotating the initial vertex
        k times. This face is non-degenerate if and only if the order of the
        rotation is strictly greater than two. Only {r, s, t} can give such faces.

        2. Three funtamental rotations {r, s, t} satifying rs = t also could generate
        some triangle faces.
        """
        for rot in ((0,), (2,), (4,)):
            order = self.rotations[rot]
            f0 = tuple(self.move(0, rot * k) for k in range(order))
            fgens = (rot,)
            coset_reps = self.get_coset_representatives(fgens, coxeter=False)
            orbit = self.get_orbit(coset_reps, f0)
            self.face_indices.append(orbit)
            self.num_faces += len(orbit)

        # handle the special triangle faces generated from
        # 1. {v0, v0s, v0rs}
        # 2. {v0, v0t, v0rt},
        # 3. {v0, v0s, v0t^-1s}
        # 4. {v0, v0rs, v0t^-1s}
        # the edges of these triangles are in different orbits
        # hence their stabilizing subgroups are all <1>.
        for triangle in [
            (0, self.move(0, (2,)), self.move(0, (0, 2))),
            (0, self.move(0, (4,)), self.move(0, (0, 4))),
            (0, self.move(0, (2,)), self.move(0, (5, 2))),
            (0, self.move(0, (0, 2)), self.move(0, (5, 2))),
        ]:
            orbit = self.get_orbit(self.vwords, triangle)
            self.face_indices.append(orbit)
            self.num_faces += len(orbit)

    def transform(self, vector, word):
        """
        The generators are 0 for r=ρ₀ρ₁, 2 for s=ρ₁ρ₂, 4 for t=ρ₁ρ₃.
        """
        for g in word:
            if g == 0:
                vector = np.dot(vector, self.reflections[0])
                vector = np.dot(vector, self.reflections[1])
            elif g == 2:
                vector = np.dot(vector, self.reflections[1])
                vector = np.dot(vector, self.reflections[2])
            else:
                vector = np.dot(vector, self.reflections[1])
                vector = np.dot(vector, self.reflections[3])
        return vector


class Catalan3D(Polyhedra):

    """Catalan solids are duals of uniform polyhedron.
    These polyhedron are face transitive but (usually) not vertex transitive.
    But to keep things consistent we still put the vertices in a 1d list.
    """

    def __init__(self, P):
        """Construct a Catalan solid form a given polyhedra `P`.
        """
        self.P = P
        self.vertices_coords = []
        self.face_indices = []

    def build_geometry(self):
        self.P.build_geometry()
        self.get_vertices()
        self.get_faces()

    def get_vertices(self):
        """Each vertex in this dual polyhedra comes from a face f in the
        original polyhedra `P`. Usually it's not the center of f but a
        scaled version of it.
        """
        for face_group in self.P.face_indices:
            for face in face_group:
                verts = [self.P.vertices_coords[ind] for ind in face]
                cen = sum(verts)
                normal = helpers.normalize(cen)
                weights = sum(np.dot(v, normal) for v in verts) / len(face)
                self.vertices_coords.append(normal / weights)

    def get_faces(self):
        """Each face f in this dual polyhedra comes from a vertex v in the
        original polyhedra `P`. The vertices in f are faces of `P` that meet at v.
        """
        def contain_edge(f, e):
            """Check if a face f contains a given edge e = (v1, v2).
            """
            v1, v2 = e
            for w1, w2 in zip(f, f[1:] + [f[0]]):
                if (v1, v2) in [(w1, w2), (w2, w1)]:
                    return True
            return False

        def is_adjacent(f1, f2):
            """Check if two faces f1, f2 are adjacent.
            """
            for e in zip(f1, f1[1:] + [f1[0]]):
                if contain_edge(f2, e):
                    return True
            return False

        result = []
        P_faces_flatten = [face for face_group in self.P.face_indices
                           for face in face_group]
        # there is a face for each vertex v in the original polyhedra P
        for k in range(len(self.P.vertices_coords)):
            # firstly we gather all faces in P that meet at v
            faces_unordered = []
            for ind, f in enumerate(P_faces_flatten):
                if k in f:
                    faces_unordered.append([ind, f])

            # then we re-align them so that they form a cycle around v
            i0, f0 = faces_unordered[0]
            face = [i0]
            current_face = f0
            while len(face) < len(faces_unordered):
                for ind, f in faces_unordered:
                    if ind not in face and is_adjacent(current_face, f):
                        face.append(ind)
                        current_face = f

            result.append(face)
        self.face_indices.append(result)
