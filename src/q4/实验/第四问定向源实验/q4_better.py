"""第二轮改进：有保证的26点布局，以及搜索期间低绕路定位插入。"""
import math
from functools import lru_cache
from q4_routes import ShiftB, triangle_intersects_disk, initial_route
from strategies import CoverageIntegratedAgent


class Grid26A(ShiftB):
    lattice_side_m = 999.0
    phase = (0.0, 1 / 6)


class Grid26B(ShiftB):
    lattice_side_m = 999.0
    phase = (0.0, 0.25)


class Grid26C(ShiftB):
    lattice_side_m = 999.0
    phase = (1 / 6, 1 / 12)


class Grid26Compact(Grid26B):
    lattice_side_m = 992.0


@lru_cache(maxsize=32)
def contracted_mesh(side, phase, radius):
    """径向内收网格；运行时核验三角形方向、边长和边界对圆盘的包含关系。"""
    height = side * math.sqrt(3) / 2
    def point(i, j):
        return (side*(i+j/2+phase[0]), height*(j+phase[1]))
    triangles = []
    for i in range(-8, 9):
        for j in range(-8, 9):
            a,b,c,d = point(i,j),point(i+1,j),point(i,j+1),point(i+1,j+1)
            for tri in ([a,b,c],[b,d,c]):
                if triangle_intersects_disk(tri):
                    triangles.append(tri)
    def project(p):
        scale = min(1.0, radius / max(math.hypot(*p), 1e-9))
        return (p[0]*scale,p[1]*scale)
    edges = {}
    min_area = math.inf
    max_length = 0.
    vertices = set()
    for tri in triangles:
        q = [project(p) for p in tri]
        vertices.update(q)
        area = (q[1][0]-q[0][0])*(q[2][1]-q[0][1])-(q[1][1]-q[0][1])*(q[2][0]-q[0][0])
        min_area = min(min_area,area)
        if area <= 1e-6:
            raise ValueError('内收导致三角形退化或翻转')
        for k in range(3):
            a,b = tri[k],tri[(k+1)%3]
            edge = tuple(sorted((a,b)))
            count,_ = edges.get(edge,(0,None))
            edges[edge] = (count+1,(project(a),project(b)))
            max_length = max(max_length,math.dist(project(a),project(b)))
    boundary = [edge for count,edge in edges.values() if count==1]
    min_support = min((a[0]*b[1]-a[1]*b[0])/math.dist(a,b) for a,b in boundary)
    # CCW边界每条有向直线都将半径1800圆盘留在左侧，且总绕数为1。
    winding = sum(math.atan2(a[0]*b[1]-a[1]*b[0],a[0]*b[0]+a[1]*b[1]) for a,b in boundary)
    assert min_support >= 1800 + 1e-6, min_support
    assert abs(winding-2*math.pi)<1e-7, winding
    assert max_length <= 1000 - 1e-6, max_length
    points = [(0.,0.)]+sorted((p for p in vertices if math.hypot(*p)>1e-7), key=lambda p:(math.hypot(*p),math.atan2(p[1],p[0])))
    return tuple(points), {'sites':len(points),'min_boundary_support_m':min_support,
                           'max_edge_m':max_length,'min_double_area':min_area,
                           'triangle_count':len(triangles),'boundary_winding':winding/(2*math.pi)}


class Contract28(ShiftB):
    contract_radius = 2100.0
    def __init__(self, sim, verbose=False):
        super().__init__(sim, verbose)
        points,self.mesh_certificate = contracted_mesh(self.lattice_side_m,self.phase,self.contract_radius)
        self.search_points = list(points)
        self.planned = initial_route(points)


class Contract28R2000(Contract28):
    contract_radius = 2000.0


class Contract26(Contract28):
    lattice_side_m = 992.0
    phase = (0.0,0.25)


class Contract26R2000(Contract26):
    contract_radius = 2000.0


class Insert28(ShiftB):
    insertion_budget_m = 200.0
    max_coverage_insertions = 12

    def _insertion_before(self, next_point):
        return CoverageIntegratedAgent._insertion_before(self, next_point)


class Insert26(Grid26B):
    insertion_budget_m = 200.0
    max_coverage_insertions = 12

    def _insertion_before(self, next_point):
        return CoverageIntegratedAgent._insertion_before(self, next_point)


class ClearEarly28(ShiftB):
    """只在已收敛到100米的频道上继续覆盖期共观测，尝试提前清除。"""
    def _coobserve(self, point, primary_channel):
        super()._coobserve(point, primary_channel)
        for channel, st in self.state.items():
            if st.cleared or not st.discovered or channel == primary_channel:
                continue
            if len(st.observations) < 2 or len(st.observations) >= 4:
                continue
            if point in st.probed_points:
                continue
            radius = self._snapshot(st).circle.radius_m
            if 19.75 < radius < 100:
                result = self.observe(point, channel)
                if result in ('direction', 'near'):
                    st.attempts += 1
                self.co_measurements += 1
