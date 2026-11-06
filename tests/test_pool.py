import pytest

from holistor_stress.core.pool import PoolExclusivo, SinFilasDisponiblesError, particionar
from test_validaciones import fila


def test_cada_fila_se_entrega_una_sola_vez():
    pool = PoolExclusivo([fila(1), fila(2)])
    a, b = pool.tomar(), pool.tomar()
    assert a.id != b.id
    assert (pool.disponibles, pool.en_uso) == (0, 2)
    with pytest.raises(SinFilasDisponiblesError, match="sesión única"):
        pool.tomar()


def test_fila_devuelta_se_reutiliza():
    pool = PoolExclusivo([fila(1)])
    f = pool.tomar()
    pool.devolver(f)
    assert pool.tomar().id == f.id


def test_no_se_puede_devolver_dos_veces():
    pool = PoolExclusivo([fila(1)])
    f = pool.tomar()
    pool.devolver(f)
    with pytest.raises(ValueError):
        pool.devolver(f)


def test_ids_repetidos():
    with pytest.raises(ValueError, match="repetidos"):
        PoolExclusivo([fila(1), fila(1)])


def test_particion_disjunta_y_completa():
    filas = [fila(i) for i in range(1, 8)]
    grupos = particionar(filas, 3)
    ids = [f.id for g in grupos for f in g]
    assert sorted(ids) == sorted(f.id for f in filas)
    assert len(ids) == len(set(ids))
    assert [len(g) for g in grupos] == [3, 2, 2]
