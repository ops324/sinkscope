"""coreアプリのテスト。

mesh_indices_from_code の往復（round-trip）テストが主目的。本AOI(東京都・埼玉県)は
投影原点(北緯36度・東経139度50分)より南西にあるため、実際のmesh_codeのix・iyは
共に負の値になる("250m--13--134"等)。単純な"-"分割はこれを壊すため、正規表現
パーサ(mesh_indices_from_code)が全ての符号の組み合わせで_mesh_codeの逆関数として
正しく機能することを確認する(analysis/permutation.pyのMoran's I計算が依存する)。
"""
from django.test import TestCase

from .mesh import _mesh_code, mesh_indices_from_code


class MeshIndicesFromCodeTests(TestCase):
    def test_round_trip_negative_indices(self):
        """本AOIの実際の値域(ix・iyとも負)での往復を確認する。"""
        for ix, iy in [(-13, -134), (-9, -129), (-31, -142)]:
            code = _mesh_code(ix, iy)
            self.assertEqual(mesh_indices_from_code(code), (ix, iy))

    def test_round_trip_all_sign_combinations(self):
        for ix, iy in [(13, 134), (-13, 134), (13, -134), (-13, -134), (0, 0)]:
            code = _mesh_code(ix, iy)
            self.assertEqual(mesh_indices_from_code(code), (ix, iy))

    def test_naive_split_would_have_failed(self):
        """回帰防止の記録：単純な"-"分割は負数のmesh_codeで壊れることを明示する
        (["250m","","13","","134"]のように空文字列を生み、位置から正しく復元できない)。
        """
        code = _mesh_code(-13, -134)
        naive_parts = code.split("-")
        self.assertNotEqual(len(naive_parts), 3, "単純split(\"-\")は負数を正しく分解できない")

    def test_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            mesh_indices_from_code("not-a-mesh-code")
