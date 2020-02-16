#/bin/bash

KEY_ID=$1
TMPDIR="$(mktemp -d)"
BASEDIR="$( cd "$(dirname "$0")" >/dev/null 2>&1 ; pwd -P )"

echo "Using following tmp dir: $TMPDIR"

## export the private key
gpg --export-secret-key $KEY_ID > $TMPDIR/privkey.org
# encode the private key as base64 and split the result into 140 char chunks
#       - base64 -w0
#           -w0: do not do any line breaks, one continous stream of chars
#       - split 
#           -b 140: 140 bytes (chars) long
#           -d: use numeric suffixes, starting at 0
cat $TMPDIR/privkey.org | base64 -w0 | split -b 140 -d - $TMPDIR/privkey.bin.
rm $TMPDIR/privkey.org

# get the total number of files generated
NUM_FILES=$(ls -1 $TMPDIR/privkey.bin.* | wc -l)

# save the payload representation of the QR codes into a text file
#    echo $(echo $K | rev | cut -d '.' -f 1 | rev): getting the number from the file suffix
#      - echo filename
#      - reverse filename
#      - cut the first field, which is delimeted by a point
#      - reverse again to get original order
#    $(cat $K | md5sum | cut -c -6): create the first six characters of the md5sum
#      - output content of the file
#      - create the md5sum
#      - cut the first six characters 
echo "Key ID: $KEY_ID" > $TMPDIR/result.txt
for K in $TMPDIR/privkey.bin.*; do echo $(echo $K | rev | cut -d '.' -f 1 | rev)/$NUM_FILES $(cat $K) $(cat $K | md5sum | cut -c -6) >> $TMPDIR/result.txt; done

# encode the payload as QR codes
#    same as above. Additionally:
#    - qrencode
#      -l H: High redundancy level for error correction (Low,Quality,High)
#      -c: ascii character mode
#      -o $K.png: output file
for K in $TMPDIR/privkey.bin.*; do echo -n $(echo $K | rev | cut -d '.' -f 1 | rev)/$NUM_FILES $(cat $K) $(cat $K | md5sum | cut -c -6) | qrencode -l H -c -o $K.png; done

# group all QR odes into one image
# montage
#   -geometry 219x219: each input image is scaled to 219x219
montage $TMPDIR/privkey.bin.*.png -geometry 219x219 $TMPDIR/result.png
# removing all single QR codes
rm $TMPDIR/privkey.bin.* 

## create printout

# convert QR code image into one A4 pdf 
convert $TMPDIR/result.png -background white -page 842x595 $TMPDIR/codes.pdf

# save textual payload representation as post script
# a2ps
#   -1: size 1
#   -r: landscape
#   -A fill: file alignment
#   -f8: font size 8
#   -o: output
a2ps -1 -r -A fill -f8 -o $TMPDIR/result.ps $TMPDIR/result.txt
rm $TMPDIR/result.txt $TMPDIR/result.png

# convert the post script file into a pdf
ps2pdf $TMPDIR/result.ps $TMPDIR/result.pdf && rm $TMPDIR/result.ps

# merge all pdfs together
pdfunite $BASEDIR/intro.pdf $TMPDIR/codes.pdf $TMPDIR/result.pdf Paperkey_$KEY_ID.pdf

# remove remaining artifacts
rm $TMPDIR/codes.pdf $TMPDIR/result.pdf
rmdir $TMPDIR
echo "The pdf to print can be found here: $TMPDIR/Paperkey_$KEY_ID.pdf".
echo "After you've printed this pdf, delete it, as it contains your private key."
