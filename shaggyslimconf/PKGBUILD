# Maintainer: John Jenkins twodopeshaggy@gmail.com

pkgname=shaggyslimconf
pkgver=20120809
pkgrel=10
pkgdesc="Slim GUI Configure"
license=('GPL')
arch=('i686' 'x86_64')
makedepends=('git')
depends=('slim' 'pygtk')
url="https://github.com/shaggytwodope/shaggyslimconf"
source=("git+git://github.com/shaggytwodope/shaggyslimconf.git")
md5sums=('SKIP')

_gitname="shaggyslimconf"


package() {   
  cd "$srcdir"
  install -D -m755 $srcdir/$_gitname/$pkgname "$pkgdir/usr/bin/$pkgname"
  install -D -m755 $srcdir/$_gitname/$pkgname-ui.glade "$pkgdir/usr/share/$pkgname/glade/$pkgname-ui.glade"
  
}  
